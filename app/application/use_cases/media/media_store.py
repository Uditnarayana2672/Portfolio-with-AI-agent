"""MediaStore — shared persistence tail for media use cases (application layer).

Both UploadMedia (multipart) and ImportUrlMedia (remote URL) converge here once
they hold validated bytes (or, for YouTube, validated metadata). It owns the
de-duplication, collision-safe public_id naming, retry/backoff upload to storage,
row insertion, and activity logging — so that logic lives in exactly one place.
"""
from __future__ import annotations

import io
import time
import uuid
from collections.abc import Callable

from app.application.dtos.media import (
    OG_IMAGE_EXPECTED_HEIGHT,
    OG_IMAGE_EXPECTED_WIDTH,
    OG_IMAGE_FOLDER,
    UPLOAD_RETRY_BACKOFF,
    UploadedAssetView,
    UploadMediaResult,
)
from app.application.interfaces.image_storage import ImageStorage, StorageError
from app.domain.entities.media_asset import MediaAsset
from app.domain.exceptions import StorageUploadError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.media_asset_repository import (
    MediaAssetRepository,
    NewMediaAsset,
)


class MediaStore:
    def __init__(
        self,
        *,
        repo: MediaAssetRepository,
        activity: ActivityLogRepository,
        storage: ImageStorage,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._repo = repo
        self._activity = activity
        self._storage = storage
        self._sleep = sleep

    # ── Cloudinary-backed binary (upload or fetched-from-URL) ────────────────
    def store_binary(
        self,
        *,
        content: bytes,
        ext: str,
        resource_type: str,
        folder: str,
        base_name: str,
        alt_text: str | None,
        uploaded_by: uuid.UUID,
        file_hash: str,
        skip_dedup: bool = False,
    ) -> UploadMediaResult:
        # De-duplicate by content hash unless the caller opts out (upload
        # endpoint always passes skip_dedup=True per spec edge-case-8).
        if not skip_dedup:
            existing = self._repo.find_by_hash(file_hash)
            if existing is not None:
                return UploadMediaResult(duplicate=True, asset=self._to_view(existing))

        folder = folder.strip().strip("/")
        stem = self._slug(self._strip_extension(base_name)) or "file"
        final_stem, renamed = self._resolve_collision(folder, stem)
        public_id = f"{folder}/{final_stem}" if folder else final_stem
        file_name = f"{final_stem}.{ext}"
        rename_note = (
            f"Renamed to {file_name} to avoid collision" if renamed else None
        )

        result = self._upload_with_retry(
            content=content, folder=folder, public_id=final_stem
        )

        # Edge case 9: OG images with wrong dimensions get a non-blocking warning.
        warnings: list[str] = []
        if folder == OG_IMAGE_FOLDER:
            w = result.get("width") or 0
            h = result.get("height") or 0
            if w != OG_IMAGE_EXPECTED_WIDTH or h != OG_IMAGE_EXPECTED_HEIGHT:
                warnings.append(
                    f"og_image dimensions should be "
                    f"{OG_IMAGE_EXPECTED_WIDTH}×{OG_IMAGE_EXPECTED_HEIGHT} "
                    f"for best social card display — got {w}×{h}"
                )

        new = NewMediaAsset(
            cloudinary_url=result.get("secure_url") or result.get("url"),
            public_id=result.get("public_id") or public_id,
            resource_type=resource_type,
            format=result.get("format") or ext,
            width=result.get("width"),
            height=result.get("height"),
            file_size=result.get("bytes") or len(content),
            file_name=file_name,
            folder=folder,
            alt_text=alt_text,
            source_type="cloudinary",
            file_hash=file_hash,
            uploaded_by=uploaded_by,
        )
        asset = self._repo.add(new)
        self._log(asset, file_name, resource_type)

        return UploadMediaResult(
            duplicate=False,
            asset=self._to_view(asset),
            renamed=renamed,
            rename_note=rename_note,
            warnings=warnings,
        )

    # ── Remote video registration (no bytes; e.g. YouTube) ──────────────────
    def store_external_video(
        self,
        *,
        external_id: str,
        folder: str,
        alt_text: str | None,
        uploaded_by: uuid.UUID,
        thumbnail_url: str | None,
        title: str | None,
        duration_seconds: int | None,
    ) -> UploadMediaResult:
        existing = self._repo.find_by_external_id(external_id)
        if existing is not None:
            return UploadMediaResult(duplicate=True, asset=self._to_view(existing))

        new = NewMediaAsset(
            cloudinary_url=None,
            public_id=None,
            resource_type="video",
            format=None,
            width=None,
            height=None,
            file_size=None,
            file_name=title,
            folder=folder.strip().strip("/"),
            alt_text=alt_text,
            source_type="youtube",
            file_hash=None,
            uploaded_by=uploaded_by,
            external_id=external_id,
            thumbnail_url=thumbnail_url,
            video_title=title,
            video_duration_seconds=duration_seconds,
        )
        asset = self._repo.add(new)
        self._log(asset, title or external_id, "video")
        return UploadMediaResult(duplicate=False, asset=self._to_view(asset), renamed=False)

    # ── helpers ─────────────────────────────────────────────────────────────
    def _upload_with_retry(
        self, *, content: bytes, folder: str, public_id: str
    ) -> dict:
        attempts = len(UPLOAD_RETRY_BACKOFF)
        last_request_id: str | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._storage.upload(
                    io.BytesIO(content),
                    folder=folder or None,
                    public_id=public_id,
                    resource_type="auto",
                )
            except StorageError as exc:
                last_request_id = exc.request_id
                if attempt < attempts:
                    self._sleep(UPLOAD_RETRY_BACKOFF[attempt - 1])
        raise StorageUploadError(
            attempts=attempts, request_id=last_request_id or uuid.uuid4().hex
        )

    def _resolve_collision(self, folder: str, stem: str) -> tuple[str, bool]:
        base_pid = f"{folder}/{stem}" if folder else stem
        if not self._repo.public_id_exists(base_pid):
            return stem, False
        n = 2
        while True:
            candidate = f"{stem}-{n}"
            pid = f"{folder}/{candidate}" if folder else candidate
            if not self._repo.public_id_exists(pid):
                return candidate, True
            n += 1

    def _log(self, asset: MediaAsset, title: str, resource_type: str) -> None:
        self._activity.record(
            action_type="media_uploaded",
            description=f"Uploaded {title}",
            entity_type="media_asset",
            entity_id=asset.id,
            entity_title=title,
            performed_by=asset.uploaded_by,
            metadata={
                "public_id": asset.public_id,
                "external_id": asset.external_id,
                "resource_type": resource_type,
                "source_type": asset.source_type,
                "file_size": asset.file_size,
            },
        )

    @staticmethod
    def _strip_extension(filename: str) -> str:
        stem, dot, _ = (filename or "").rpartition(".")
        return stem if dot else (filename or "")

    @staticmethod
    def _slug(value: str) -> str:
        return "-".join(value.strip().split())

    @staticmethod
    def _to_view(asset: MediaAsset) -> UploadedAssetView:
        return UploadedAssetView(
            id=asset.id,
            cloudinary_url=asset.cloudinary_url,
            public_id=asset.public_id,
            resource_type=asset.resource_type,
            format=asset.format,
            width=asset.width,
            height=asset.height,
            file_size=asset.file_size,
            file_name=asset.file_name,
            folder=asset.folder,
            alt_text=asset.alt_text,
            file_hash=asset.file_hash,
            uploaded_by=asset.uploaded_by,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            source_type=asset.source_type,
            external_id=asset.external_id,
            thumbnail_url=asset.thumbnail_url,
            video_title=asset.video_title,
            video_duration_seconds=asset.video_duration_seconds,
        )

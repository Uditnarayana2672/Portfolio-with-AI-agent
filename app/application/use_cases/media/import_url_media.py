"""ImportUrlMedia use case (application layer).

Imports a media asset from a remote URL. Two branches:

  • YouTube link  → register the video by id (no bytes fetched), enriching it
                    with title/thumbnail/duration metadata.
  • everything else → fetch the bytes through the SSRF-safe UrlFetcher, sniff the
                    *real* type from magic bytes, enforce the type/size rules,
                    then hand off to the shared MediaStore.

The security-critical fetching (scheme/host/IP checks, redirects, timeouts,
streamed cap) lives behind the UrlFetcher port — this use case stays pure.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from urllib.parse import unquote, urlsplit

from app.application.dtos.media import (
    ALLOWED_EXTENSIONS,
    EXTENSION_RESOURCE_TYPE,
    VIDEO_MAX_BYTES,
    ImportUrlCommand,
    UploadMediaResult,
)
from app.application.interfaces.image_storage import ImageStorage
from app.application.interfaces.url_fetcher import UrlFetcher
from app.application.interfaces.video_metadata import VideoMetadataProvider
from app.application.use_cases.media.file_type import guess_label, sniff_extension
from app.application.use_cases.media.media_store import MediaStore
from app.application.use_cases.media.upload_media import enforce_size
from app.application.use_cases.media.youtube_url import parse_youtube_id
from app.domain.exceptions import InvalidUrlError, UnsupportedFileTypeError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.media_asset_repository import MediaAssetRepository


class ImportUrlMedia:
    def __init__(
        self,
        *,
        repo: MediaAssetRepository,
        activity: ActivityLogRepository,
        storage: ImageStorage,
        fetcher: UrlFetcher,
        video_metadata: VideoMetadataProvider,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._repo = repo
        self._fetcher = fetcher
        self._video_metadata = video_metadata
        self._store = MediaStore(
            repo=repo, activity=activity, storage=storage, sleep=sleep
        )

    def execute(self, cmd: ImportUrlCommand) -> UploadMediaResult:
        url = (cmd.url or "").strip()
        if not url:
            raise InvalidUrlError("URL is required")

        youtube_id = parse_youtube_id(url)
        if youtube_id is not None:
            return self._import_youtube(youtube_id, cmd)
        return self._import_binary(url, cmd)

    # ── YouTube branch ──────────────────────────────────────────────────────
    def _import_youtube(self, video_id: str, cmd: ImportUrlCommand) -> UploadMediaResult:
        meta = self._video_metadata.fetch(video_id)
        return self._store.store_external_video(
            external_id=video_id,
            folder=cmd.folder,
            alt_text=cmd.alt_text,
            uploaded_by=cmd.uploaded_by,
            thumbnail_url=meta.thumbnail_url,
            title=meta.title,
            duration_seconds=meta.duration_seconds,
        )

    # ── Remote-binary branch (SSRF-safe fetch) ──────────────────────────────
    def _import_binary(self, url: str, cmd: ImportUrlCommand) -> UploadMediaResult:
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ("http", "https"):
            # Fail fast on obviously-bad schemes before touching the network.
            raise InvalidUrlError(f"Unsupported URL scheme: {scheme or 'none'!r}")

        # Hard cap the download at the largest allowed size (video). The
        # type-specific cap is re-checked below once we know the real type.
        fetched = self._fetcher.fetch(url, max_bytes=VIDEO_MAX_BYTES)
        content = fetched.content

        # Trust the bytes, not the URL/extension or the declared Content-Type.
        ext = sniff_extension(content)
        if ext is None or ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                got=guess_label(fetched.content_type), allowed=ALLOWED_EXTENSIONS
            )

        resource_type = EXTENSION_RESOURCE_TYPE[ext]
        enforce_size(len(content), resource_type)

        file_hash = hashlib.sha256(content).hexdigest()
        base_name = self._base_name_from_url(fetched.final_url or url)

        return self._store.store_binary(
            content=content,
            ext=ext,
            resource_type=resource_type,
            folder=cmd.folder,
            base_name=base_name,
            alt_text=cmd.alt_text,
            uploaded_by=cmd.uploaded_by,
            file_hash=file_hash,
        )

    @staticmethod
    def _base_name_from_url(url: str) -> str:
        """Derive a public_id stem from the URL's last path segment."""
        path = urlsplit(url).path
        last = unquote(path.rsplit("/", 1)[-1]) if path else ""
        stem = last.rsplit(".", 1)[0] if "." in last else last
        return stem or "import"

"""UpdateMedia use case (application layer).

Backs PATCH /admin/media/{id}: edit an asset's alt text, file name, or folder.
Changing the file name OR the folder renames the Cloudinary ``public_id`` in
place (Cloudinary's rename API — not a re-upload). On a name collision the new
stem gets a numeric suffix instead of overwriting an existing asset. Because a
rename invalidates the old derived/transformed CDN URLs, the refreshed asset
carries the fresh ``cloudinary_url``.

No SQL, no HTTP, no Cloudinary imports here — only the repository and the
storage port.
"""
from __future__ import annotations

import re

from app.application.dtos.media import (
    UNSET,
    UpdateMediaCommand,
    UpdateMediaResult,
)
from app.application.interfaces.image_storage import ImageStorage
from app.application.use_cases.media.media_view import to_media_view
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.repositories.media_asset_repository import MediaAssetRepository

# A folder is one or more "/"-separated segments of url-safe characters.
_FOLDER_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def _normalize_folder(raw: str) -> str:
    """Trim/collapse a folder path and validate each segment. Raises
    ValidationError (→ 400 INVALID_FOLDER) for an empty or malformed path."""
    segments = [s for s in raw.strip().strip("/").split("/") if s]
    if not segments or any(not _FOLDER_SEGMENT.match(s) for s in segments):
        raise ValidationError(f"Invalid folder: {raw!r}")
    return "/".join(segments)


def _slug(value: str) -> str:
    """Collapse whitespace runs to single hyphens (matches the upload slugger)."""
    return "-".join(value.strip().split())


def _stem_and_ext(file_name: str) -> tuple[str, str]:
    """Split a file name into its stem and lowercased extension (no dot)."""
    stem, dot, ext = (file_name or "").rpartition(".")
    return (stem, ext.lower()) if dot else (file_name or "", "")


class UpdateMedia:
    def __init__(self, *, repo: MediaAssetRepository, storage: ImageStorage) -> None:
        self._repo = repo
        self._storage = storage

    def execute(self, cmd: UpdateMediaCommand) -> UpdateMediaResult:
        item = self._repo.get(cmd.asset_id)
        if item is None:
            raise NotFoundError(f"No media asset with id {cmd.asset_id}")
        asset = item.asset

        changes: dict = {}
        renamed = False
        rename_note: str | None = None

        # alt_text is free-form and may be cleared to null.
        if cmd.alt_text is not UNSET:
            changes["alt_text"] = cmd.alt_text

        # A file_name or folder edit drives the rename/move.
        if cmd.file_name is not UNSET or cmd.folder is not UNSET:
            new_folder = (
                _normalize_folder(cmd.folder)
                if cmd.folder is not UNSET
                else asset.folder
            )
            current_stem, current_ext = _stem_and_ext(asset.file_name or "")
            # Cloudinary's rename can't change the format, so keep the original
            # extension regardless of any extension the client typed.
            ext = current_ext or (asset.format or "")
            if cmd.file_name is not UNSET:
                raw_stem, _ = _stem_and_ext(cmd.file_name)
                new_stem = _slug(raw_stem) or "file"
            else:
                new_stem = current_stem

            if asset.public_id and asset.source_type == "cloudinary":
                renamed, rename_note, rename_changes = self._rename_on_cdn(
                    asset_public_id=asset.public_id,
                    resource_type=asset.resource_type,
                    new_folder=new_folder,
                    new_stem=new_stem,
                    ext=ext,
                )
                changes.update(rename_changes)
            else:
                # YouTube/no-CDN asset: there is no public_id to rename, so just
                # persist the display fields the client changed.
                if cmd.folder is not UNSET:
                    changes["folder"] = new_folder
                if cmd.file_name is not UNSET:
                    changes["file_name"] = cmd.file_name

        if changes:
            updated = self._repo.update(cmd.asset_id, changes)
            if updated is None:  # raced with a delete between fetch and update
                raise NotFoundError(f"No media asset with id {cmd.asset_id}")
            item = updated

        return UpdateMediaResult(
            asset=to_media_view(item),
            renamed=renamed,
            rename_note=rename_note,
        )

    def _rename_on_cdn(
        self,
        *,
        asset_public_id: str,
        resource_type: str,
        new_folder: str,
        new_stem: str,
        ext: str,
    ) -> tuple[bool, str | None, dict]:
        """Move the Cloudinary asset to ``{new_folder}/{new_stem}`` (suffixing on
        collision) and return (renamed, rename_note, column-changes). A no-op
        when the target equals the current public_id."""
        base_target = f"{new_folder}/{new_stem}" if new_folder else new_stem
        if base_target == asset_public_id:
            return False, None, {}

        final_stem, target_public_id, renamed = self._resolve_target(
            new_folder, new_stem
        )
        result = self._storage.rename(
            asset_public_id,
            target_public_id,
            resource_type=resource_type,
        )

        changes: dict = {
            "public_id": result.get("public_id") or target_public_id,
            "folder": new_folder,
            "file_name": f"{final_stem}.{ext}" if ext else final_stem,
        }
        fresh_url = result.get("secure_url") or result.get("url")
        if fresh_url:
            changes["cloudinary_url"] = fresh_url

        rename_note = (
            f"Renamed to {final_stem} to avoid collision in {new_folder}"
            if renamed
            else None
        )
        return renamed, rename_note, changes

    def _resolve_target(self, folder: str, stem: str) -> tuple[str, str, bool]:
        """Return (stem, public_id, suffixed?) — appending ``-2``, ``-3``, … only
        if another asset already owns the target public_id."""
        base = f"{folder}/{stem}" if folder else stem
        if not self._repo.public_id_exists(base):
            return stem, base, False
        n = 2
        while True:
            candidate = f"{stem}-{n}"
            pid = f"{folder}/{candidate}" if folder else candidate
            if not self._repo.public_id_exists(pid):
                return candidate, pid, True
            n += 1

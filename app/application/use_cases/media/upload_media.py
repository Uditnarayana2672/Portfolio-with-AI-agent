"""UploadMedia use case (application layer).

Validates an uploaded file's type & size and computes its content hash, then
hands the bytes to the shared MediaStore (de-dup → collision-safe naming →
retry upload → persist → log). No SQL, no HTTP, no Cloudinary imports.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

from app.application.dtos.media import (
    ALLOWED_EXTENSIONS,
    ALLOWED_FOLDERS,
    EXTENSION_RESOURCE_TYPE,
    IMAGE_MAX_BYTES,
    VALID_RESOURCE_TYPES,
    VIDEO_MAX_BYTES,
    UploadMediaCommand,
    UploadMediaResult,
)
from app.application.interfaces.image_storage import ImageStorage
from app.application.use_cases.media.media_store import MediaStore
from app.domain.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    InvalidFolderError,
    ResourceTypeMismatchError,
    UnsupportedFileTypeError,
)
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.media_asset_repository import MediaAssetRepository


def humanize_limit(max_bytes: int) -> str:
    """A coarse '20 MB' / '200 MB' label for the size-limit error body."""
    return f"{max_bytes // (1024 * 1024)} MB"


def resolve_resource_type(declared: str | None, ext: str) -> str:
    """Declared resource_type wins when valid; otherwise infer from extension."""
    if declared is not None and declared in VALID_RESOURCE_TYPES:
        return declared
    return EXTENSION_RESOURCE_TYPE[ext]


def enforce_size(content_len: int, resource_type: str) -> None:
    """Raise FileTooLargeError if the bytes exceed the cap for this type."""
    max_bytes = VIDEO_MAX_BYTES if resource_type == "video" else IMAGE_MAX_BYTES
    if content_len > max_bytes:
        raise FileTooLargeError(max_bytes=max_bytes, limit=humanize_limit(max_bytes))


def extension_of(filename: str) -> str:
    _, dot, ext = (filename or "").rpartition(".")
    return ext.lower() if dot else ""


class UploadMedia:
    def __init__(
        self,
        *,
        repo: MediaAssetRepository,
        activity: ActivityLogRepository,
        storage: ImageStorage,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = MediaStore(
            repo=repo, activity=activity, storage=storage, sleep=sleep
        )

    def execute(self, cmd: UploadMediaCommand) -> UploadMediaResult:
        # Edge case 1: empty file must be rejected before any other check.
        if len(cmd.content) == 0:
            raise EmptyFileError("Uploaded file is empty")

        # Edge case 4/5: folder is required and must be from the allowed list.
        folder = cmd.folder.strip().strip("/")
        if folder not in ALLOWED_FOLDERS:
            raise InvalidFolderError(folder=folder, allowed=ALLOWED_FOLDERS)

        ext = extension_of(cmd.original_filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(got=ext or "unknown", allowed=ALLOWED_EXTENSIONS)

        # Edge case 6: declared resource_type must agree with the file extension.
        inferred_type = EXTENSION_RESOURCE_TYPE[ext]
        if cmd.resource_type is not None and cmd.resource_type in VALID_RESOURCE_TYPES:
            if cmd.resource_type != inferred_type:
                raise ResourceTypeMismatchError(
                    declared=cmd.resource_type,
                    inferred=inferred_type,
                    ext=ext,
                )

        resource_type = resolve_resource_type(cmd.resource_type, ext)
        enforce_size(len(cmd.content), resource_type)

        file_hash = hashlib.sha256(cmd.content).hexdigest()
        base_name = cmd.file_name or cmd.original_filename

        # Edge case 8: skip hash-based deduplication so that uploading the same
        # file twice always creates two separate rows (spec §edge-case-8).
        return self._store.store_binary(
            content=cmd.content,
            ext=ext,
            resource_type=resource_type,
            folder=folder,
            base_name=base_name,
            alt_text=cmd.alt_text,
            uploaded_by=cmd.uploaded_by,
            file_hash=file_hash,
            skip_dedup=True,
        )

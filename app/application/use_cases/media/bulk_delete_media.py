"""Bulk-delete selected media assets while reporting expected per-item skips."""
from __future__ import annotations

from app.application.dtos.media import (
    BulkDeleteMediaCommand,
    BulkDeleteMediaResult,
    BulkDeleteSkippedItem,
)
from app.application.interfaces.image_storage import StorageError
from app.application.use_cases.media.delete_media import DeleteMedia
from app.domain.exceptions import MediaInUseError, NotFoundError


class BulkDeleteMedia:
    """Compose the single-delete policy without duplicating its side effects."""

    def __init__(self, *, delete_media: DeleteMedia) -> None:
        self._delete_media = delete_media

    def execute(self, cmd: BulkDeleteMediaCommand) -> BulkDeleteMediaResult:
        deleted = []
        skipped = []
        freed_bytes = 0
        seen = set()

        for asset_id in cmd.asset_ids:
            # The bulk bar should not produce contradictory outcomes when a
            # client accidentally submits the same selected id more than once.
            if asset_id in seen:
                continue
            seen.add(asset_id)

            try:
                asset = self._delete_media.execute_by_id(
                    asset_id,
                    force=cmd.force,
                    performed_by=cmd.performed_by,
                )
            except MediaInUseError as exc:
                skipped.append(
                    BulkDeleteSkippedItem(
                        id=asset_id,
                        reason="MEDIA_IN_USE",
                        usage_count=exc.usage_count,
                        references=exc.references,
                    )
                )
            except NotFoundError:
                skipped.append(
                    BulkDeleteSkippedItem(id=asset_id, reason="MEDIA_NOT_FOUND")
                )
            except StorageError:
                skipped.append(
                    BulkDeleteSkippedItem(id=asset_id, reason="STORAGE_ERROR")
                )
            else:
                deleted.append(asset_id)
                freed_bytes += asset.file_size or 0

        return BulkDeleteMediaResult(
            deleted=deleted,
            skipped=skipped,
            deleted_count=len(deleted),
            freed_bytes=freed_bytes,
        )

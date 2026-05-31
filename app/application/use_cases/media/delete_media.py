"""DeleteMedia use case (application layer).

Backs DELETE /admin/media/{public_id} and DELETE /admin/media/by-id/{asset_id}:
remove one asset plus its DB row, recording a ``media_deleted`` entry. Cloudinary
assets also have their derived/transformed URLs removed. By default the delete is
refused (409) while the asset is still referenced; pass ``force=True`` to bypass
that guard.

No SQL, no HTTP, no Cloudinary imports — only the repository and storage ports.
"""
from __future__ import annotations

import uuid

from app.application.interfaces.image_storage import ImageStorage
from app.application.use_cases.media.usage_view import to_usage_reference_view
from app.domain.entities.media_asset import MediaAsset
from app.domain.exceptions import MediaInUseError, NotFoundError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.media_asset_repository import MediaAssetRepository


class DeleteMedia:
    def __init__(
        self,
        *,
        repo: MediaAssetRepository,
        activity: ActivityLogRepository,
        storage: ImageStorage,
    ) -> None:
        self._repo = repo
        self._activity = activity
        self._storage = storage

    def execute(
        self,
        public_id: str,
        *,
        force: bool = False,
        performed_by: uuid.UUID | None = None,
    ) -> None:
        asset = self._repo.find_by_public_id(public_id)
        if asset is None:
            raise NotFoundError(f"No media asset with public_id {public_id!r}")
        self._delete(asset, force=force, performed_by=performed_by)

    def execute_by_id(
        self,
        asset_id: uuid.UUID,
        *,
        force: bool = False,
        performed_by: uuid.UUID | None = None,
    ) -> None:
        item = self._repo.get(asset_id)
        if item is None:
            raise NotFoundError(f"No media asset with id {asset_id!r}")
        self._delete(item.asset, force=force, performed_by=performed_by)

    def _delete(
        self,
        asset: MediaAsset,
        *,
        force: bool,
        performed_by: uuid.UUID | None,
    ) -> None:
        # In-use guard: refuse while referenced unless the caller forces it.
        if not force and asset.public_id:
            refs = self._repo.find_usage(asset.public_id)
            if refs:
                raise MediaInUseError(
                    usage_count=len(refs),
                    references=[to_usage_reference_view(ref) for ref in refs],
                )

        # Remove the CDN object first (along with its derived/transformed URLs).
        # A "not found" from the provider is not an error — it leaves us free to
        # drop the now-orphaned row. Only delete the row once the CDN is clear,
        # so a provider failure never leaves a dangling DB record.
        if asset.public_id:
            self._storage.delete(asset.public_id)

        self._repo.delete(asset.id)

        title = asset.file_name or asset.public_id or str(asset.id)
        self._activity.record(
            action_type="media_deleted",
            description=f"Deleted {title}",
            entity_type="media_asset",
            entity_id=asset.id,
            entity_title=title,
            performed_by=performed_by,
            metadata={
                "public_id": asset.public_id,
                "resource_type": asset.resource_type,
                "source_type": asset.source_type,
                "file_size": asset.file_size,
                "forced": force,
            },
        )

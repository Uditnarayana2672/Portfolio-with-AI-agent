"""GetMediaUsage use case (application layer).

Resolves every place an asset is referenced (the "Used in N places" list shown
in the drawer and the delete-confirm modal). Raises NotFoundError for an unknown
id. Translates raw repository refs into views carrying an admin deep link.
"""
from __future__ import annotations

import uuid

from app.application.dtos.media import MediaUsageResult
from app.application.use_cases.media.usage_view import to_usage_reference_view
from app.domain.exceptions import NotFoundError
from app.domain.repositories.media_asset_repository import MediaAssetRepository


class GetMediaUsage:
    def __init__(self, repo: MediaAssetRepository) -> None:
        self._repo = repo

    def execute(self, asset_id: uuid.UUID) -> MediaUsageResult:
        item = self._repo.get(asset_id)
        if item is None:
            raise NotFoundError(f"No media asset with id {asset_id}")

        public_id = item.asset.public_id
        refs = self._repo.find_usage(public_id) if public_id else []
        references = [to_usage_reference_view(ref) for ref in refs]
        return MediaUsageResult(
            asset_id=asset_id,
            usage_count=len(references),
            references=references,
        )

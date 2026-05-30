"""GetMediaAsset use case (application layer).

Fetches one asset for the detail drawer and enriches it with a usage total.
Raises NotFoundError when the id doesn't exist (mapped to 404 at the edge).
"""
from __future__ import annotations

import uuid

from app.application.dtos.media import MediaAssetDetailResult
from app.application.use_cases.media.media_view import to_media_view
from app.domain.exceptions import NotFoundError
from app.domain.repositories.media_asset_repository import MediaAssetRepository


class GetMediaAsset:
    def __init__(self, repo: MediaAssetRepository) -> None:
        self._repo = repo

    def execute(self, asset_id: uuid.UUID) -> MediaAssetDetailResult:
        item = self._repo.get(asset_id)
        if item is None:
            raise NotFoundError(f"No media asset with id {asset_id}")
        usage_count = self._repo.usage_count(item.asset)
        return MediaAssetDetailResult(
            asset=to_media_view(item), usage_count=usage_count
        )

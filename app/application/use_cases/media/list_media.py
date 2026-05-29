"""ListMedia use case (application layer).

Validates & normalises the query, asks the repository for a page of results
plus global stats, and maps domain entities into response DTOs. No SQL, no
HTTP, no framework imports.
"""
from __future__ import annotations

from app.application.dtos.media import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    VALID_ORDER,
    VALID_RESOURCE_TYPES,
    VALID_SORT_BY,
    ListMediaQuery,
    ListMediaResult,
    MediaAssetView,
)
from app.domain.exceptions import ValidationError
from app.domain.repositories.media_asset_repository import (
    MediaAssetListItem,
    MediaAssetRepository,
)


class ListMedia:
    def __init__(self, repo: MediaAssetRepository) -> None:
        self._repo = repo

    def execute(self, query: ListMediaQuery) -> ListMediaResult:
        # ── Validate enumerated params → 400 INVALID_QUERY_PARAM ──
        if query.sort_by not in VALID_SORT_BY:
            raise ValidationError(f"Invalid sort_by '{query.sort_by}'")
        if query.order not in VALID_ORDER:
            raise ValidationError(f"Invalid order '{query.order}'")
        if query.resource_type is not None and query.resource_type not in VALID_RESOURCE_TYPES:
            raise ValidationError(f"Invalid resource_type '{query.resource_type}'")

        # ── Normalise pagination: clamp page≥1 and 1≤limit≤MAX_LIMIT ──
        page = max(1, query.page)
        limit = min(max(1, query.limit), MAX_LIMIT)
        offset = (page - 1) * limit

        # `search` empty string → treat as no search.
        search = query.search.strip() if query.search and query.search.strip() else None
        folder = query.folder or None

        page_result = self._repo.list(
            folder=folder,
            resource_type=query.resource_type,
            search=search,
            sort_by=query.sort_by,
            order=query.order,
            offset=offset,
            limit=limit,
        )

        return ListMediaResult(
            assets=[self._to_view(item) for item in page_result.items],
            total=page_result.total,
            page=page,
            limit=limit,
            # Stats are global (filters ignored) so the sidebar/pills stay
            # populated even on an empty filtered result.
            folder_stats=self._repo.folder_stats(),
            type_stats=self._repo.type_stats(),
        )

    @staticmethod
    def _to_view(item: MediaAssetListItem) -> MediaAssetView:
        a = item.asset
        return MediaAssetView(
            id=a.id,
            cloudinary_url=a.cloudinary_url,
            public_id=a.public_id,
            resource_type=a.resource_type,
            format=a.format,
            width=a.width,
            height=a.height,
            file_size=a.file_size,
            file_name=a.file_name,
            folder=a.folder,
            alt_text=a.alt_text,
            source_type=a.source_type,
            thumbnail_url=a.thumbnail_url,
            video_duration_seconds=a.video_duration_seconds,
            is_orphan=a.is_orphan,
            cdn_status="missing" if a.is_orphan else "ok",
            uploaded_by=a.uploaded_by,
            uploaded_by_name=item.uploaded_by_name,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )

"""Shared mapper: MediaAssetListItem → MediaAssetView (application layer).

Both the list endpoint and the single-asset drawer must emit the exact same
§3.1 asset shape, so the mapping (including the derived ``cdn_status``) lives in
one place.
"""
from __future__ import annotations

from app.application.dtos.media import MediaAssetView
from app.domain.repositories.media_asset_repository import MediaAssetListItem


def to_media_view(item: MediaAssetListItem) -> MediaAssetView:
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

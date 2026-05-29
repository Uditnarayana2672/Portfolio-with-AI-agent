"""SQLAlchemy implementation of MediaAssetRepository (infrastructure layer)."""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.domain.entities.media_asset import MediaAsset
from app.domain.repositories.media_asset_repository import (
    MediaAssetListItem,
    MediaAssetRepository,
    MediaListPage,
)
from app.infrastructure.persistence.orm.models import MediaAssets, ResourceType, Users

# Maps the API's sort_by values to ORM columns. The use case has already
# validated the key is one of these before we get here.
_SORT_COLUMNS = {
    "created_at": MediaAssets.created_at,
    "file_size": MediaAssets.file_size,
    "file_name": MediaAssets.file_name,
}


class SqlAlchemyMediaAssetRepository(MediaAssetRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(
        self,
        *,
        folder: str | None,
        resource_type: str | None,
        search: str | None,
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> MediaListPage:
        conditions = self._conditions(folder, resource_type, search)

        total = self._db.scalar(
            select(func.count()).select_from(MediaAssets).where(*conditions)
        ) or 0

        direction = asc if order == "asc" else desc
        stmt = (
            select(MediaAssets, Users.name)
            .outerjoin(Users, MediaAssets.uploaded_by == Users.id)
            .where(*conditions)
            .order_by(direction(_SORT_COLUMNS[sort_by]))
            .offset(offset)
            .limit(limit)
        )
        rows = self._db.execute(stmt).all()
        items = [
            MediaAssetListItem(asset=self._to_entity(asset), uploaded_by_name=name)
            for asset, name in rows
        ]
        return MediaListPage(items=items, total=total)

    def folder_stats(self) -> dict[str, int]:
        rows = self._db.execute(
            select(MediaAssets.folder, func.count()).group_by(MediaAssets.folder)
        ).all()
        stats = {folder: count for folder, count in rows}
        stats["all"] = sum(stats.values())
        return stats

    def type_stats(self) -> dict[str, int]:
        rows = self._db.execute(
            select(MediaAssets.resource_type, func.count()).group_by(MediaAssets.resource_type)
        ).all()
        return {self._enum_value(rt): count for rt, count in rows}

    # ── helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _conditions(folder: str | None, resource_type: str | None, search: str | None):
        conditions = []
        if folder:
            conditions.append(MediaAssets.folder == folder)
        if resource_type:
            conditions.append(MediaAssets.resource_type == ResourceType(resource_type))
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    MediaAssets.file_name.ilike(like),
                    MediaAssets.alt_text.ilike(like),
                    MediaAssets.public_id.ilike(like),
                )
            )
        return conditions

    @staticmethod
    def _enum_value(value) -> str:
        return value.value if hasattr(value, "value") else value

    @classmethod
    def _to_entity(cls, m: MediaAssets) -> MediaAsset:
        return MediaAsset(
            id=m.id,
            cloudinary_url=m.cloudinary_url,
            public_id=m.public_id,
            resource_type=cls._enum_value(m.resource_type),
            format=m.format,
            width=m.width,
            height=m.height,
            file_size=m.file_size,
            file_name=m.file_name,
            folder=m.folder,
            alt_text=m.alt_text,
            source_type=m.source_type,
            external_id=m.external_id,
            thumbnail_url=m.thumbnail_url,
            video_title=m.video_title,
            video_duration_seconds=m.video_duration_seconds,
            file_hash=m.file_hash,
            is_orphan=m.is_orphan,
            uploaded_by=m.uploaded_by,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

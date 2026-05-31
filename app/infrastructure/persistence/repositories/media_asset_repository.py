"""SQLAlchemy implementation of MediaAssetRepository (infrastructure layer)."""
from __future__ import annotations

import datetime

from sqlalchemy import Text, asc, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from app.domain.entities.media_asset import MediaAsset
from app.domain.repositories.media_asset_repository import (
    MediaAssetListItem,
    MediaAssetRepository,
    MediaListPage,
    MediaStatsSnapshot,
    MediaUsageRef,
    NewMediaAsset,
)
from app.infrastructure.persistence.orm.models import (
    BlogPosts,
    MediaAssets,
    ProjectBlocks,
    Projects,
    ResourceType,
    Users,
)

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

    def stats(self) -> MediaStatsSnapshot:
        # "Today" is the current UTC calendar day — created_at is timestamptz, so
        # we anchor the boundary in UTC to match how timestamps are emitted (…Z).
        today_start = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # One round-trip: total, today's additions, summed bytes, orphans, and a
        # per-type breakdown via conditional aggregates (Postgres FILTER).
        total, added_today, used_bytes, orphans, img, vid, raw = self._db.execute(
            select(
                func.count(),
                func.count().filter(MediaAssets.created_at >= today_start),
                func.coalesce(func.sum(MediaAssets.file_size), 0),
                func.count().filter(MediaAssets.is_orphan.is_(True)),
                func.count().filter(MediaAssets.resource_type == ResourceType.IMAGE),
                func.count().filter(MediaAssets.resource_type == ResourceType.VIDEO),
                func.count().filter(MediaAssets.resource_type == ResourceType.RAW),
            )
        ).one()

        return MediaStatsSnapshot(
            total_assets=total,
            added_today=added_today,
            counts={"image": img, "video": vid, "raw": raw},
            used_bytes=int(used_bytes),
            orphan_count=orphans,
        )

    def get(self, asset_id) -> MediaAssetListItem | None:
        row = self._db.execute(
            select(MediaAssets, Users.name)
            .outerjoin(Users, MediaAssets.uploaded_by == Users.id)
            .where(MediaAssets.id == asset_id)
        ).first()
        if row is None:
            return None
        asset, name = row
        return MediaAssetListItem(asset=self._to_entity(asset), uploaded_by_name=name)

    def find_usage(self, public_id: str) -> list[MediaUsageRef]:
        # A blank public_id (e.g. a YouTube asset) would make strpos(col, '')
        # match every row, so short-circuit to "no references".
        if not public_id:
            return []

        refs: list[MediaUsageRef] = []

        # 1) project thumbnails
        for pid, title in self._db.execute(
            select(Projects.id, Projects.title).where(
                func.strpos(Projects.thumbnail_url, public_id) > 0
            )
        ).all():
            refs.append(
                MediaUsageRef(kind="project", entity_id=pid, title=title, location="thumbnail")
            )

        # 2) project block configs (JSONB → text); location is the block's type
        for proj_id, title, block_type in self._db.execute(
            select(ProjectBlocks.project_id, Projects.title, ProjectBlocks.block_type)
            .join(Projects, ProjectBlocks.project_id == Projects.id)
            .where(func.strpos(cast(ProjectBlocks.config, Text), public_id) > 0)
        ).all():
            refs.append(
                MediaUsageRef(
                    kind="project",
                    entity_id=proj_id,
                    title=title,
                    location=f"{block_type} block",
                )
            )

        # 3) blog cover images
        for bid, title in self._db.execute(
            select(BlogPosts.id, BlogPosts.title).where(
                func.strpos(BlogPosts.cover_image_url, public_id) > 0
            )
        ).all():
            refs.append(
                MediaUsageRef(kind="blog", entity_id=bid, title=title, location="cover")
            )

        # 4) blog OG images (distinct 'og' kind so the UI can label it)
        for bid, title in self._db.execute(
            select(BlogPosts.id, BlogPosts.title).where(
                func.strpos(BlogPosts.og_image_url, public_id) > 0
            )
        ).all():
            refs.append(
                MediaUsageRef(kind="og", entity_id=bid, title=title, location="og:image")
            )

        # 5) blog post content (JSONB → text)
        for bid, title in self._db.execute(
            select(BlogPosts.id, BlogPosts.title).where(
                func.strpos(cast(BlogPosts.content, Text), public_id) > 0
            )
        ).all():
            refs.append(
                MediaUsageRef(kind="blog", entity_id=bid, title=title, location="content")
            )

        return refs

    def find_by_hash(self, file_hash: str) -> MediaAsset | None:
        row = self._db.scalar(
            select(MediaAssets).where(MediaAssets.file_hash == file_hash).limit(1)
        )
        return self._to_entity(row) if row is not None else None

    def public_id_exists(self, public_id: str) -> bool:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(MediaAssets)
                .where(MediaAssets.public_id == public_id)
            )
            or 0
        ) > 0

    def find_by_external_id(self, external_id: str) -> MediaAsset | None:
        row = self._db.scalar(
            select(MediaAssets).where(MediaAssets.external_id == external_id).limit(1)
        )
        return self._to_entity(row) if row is not None else None

    def find_by_public_id(self, public_id: str) -> MediaAsset | None:
        row = self._db.scalar(
            select(MediaAssets).where(MediaAssets.public_id == public_id).limit(1)
        )
        return self._to_entity(row) if row is not None else None

    def add(self, new: NewMediaAsset) -> MediaAsset:
        row = MediaAssets(
            cloudinary_url=new.cloudinary_url,
            public_id=new.public_id,
            resource_type=ResourceType(new.resource_type),
            format=new.format,
            width=new.width,
            height=new.height,
            file_size=new.file_size,
            file_name=new.file_name,
            folder=new.folder,
            alt_text=new.alt_text,
            source_type=new.source_type,
            file_hash=new.file_hash,
            uploaded_by=new.uploaded_by,
            external_id=new.external_id,
            thumbnail_url=new.thumbnail_url,
            video_title=new.video_title,
            video_duration_seconds=new.video_duration_seconds,
        )
        self._db.add(row)
        # Flush (not commit) so the DB assigns id/created_at while leaving the
        # request's transaction open — get_db commits once the request succeeds.
        self._db.flush()
        self._db.refresh(row)
        return self._to_entity(row)

    def update(self, asset_id, changes: dict) -> MediaAssetListItem | None:
        row = self._db.get(MediaAssets, asset_id)
        if row is None:
            return None
        for column, value in changes.items():
            setattr(row, column, value)
        # The column has no onupdate trigger, so bump it here per the contract.
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        # Flush only — the request's transaction stays open (get_db commits).
        self._db.flush()
        # Re-read through the uploader join so the returned item carries the name.
        return self.get(asset_id)

    def delete(self, asset_id) -> None:
        row = self._db.get(MediaAssets, asset_id)
        if row is None:
            return
        self._db.delete(row)
        # Flush so a later activity-log insert in the same request sees the row
        # gone; the request's transaction owns the commit.
        self._db.flush()

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

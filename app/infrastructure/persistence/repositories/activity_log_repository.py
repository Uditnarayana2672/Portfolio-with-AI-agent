"""SQLAlchemy implementation of ActivityLogRepository (infrastructure layer)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.repositories.activity_log_repository import ActivityEntry, ActivityLogRepository
from app.infrastructure.persistence.orm.models import (
    ActivityLog,
    ActivityType,
    BlogPosts,
    MediaAssets,
    ProjectStatus,
    Projects,
)
from app.infrastructure.persistence.repositories.site_build_repository import (
    QUIET_PERIOD_SECONDS,
    SqlAlchemySiteBuildRepository,
    sites_for_activity,
)

# entity_type values that point at a table row, for the "does it still exist" check.
_ENTITY_MODELS = {"project": Projects, "blog_post": BlogPosts, "media_asset": MediaAssets}


class SqlAlchemyActivityLogRepository(ActivityLogRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        *,
        action_type: str,
        description: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        entity_title: str | None = None,
        performed_by: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> None:
        row = ActivityLog(
            action_type=ActivityType(action_type),
            description=description,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_title=entity_title,
            performed_by=performed_by,
            metadata_=metadata or {},
        )
        self._db.add(row)
        # Same session/transaction as the media insert — the request commits both
        # together (see get_db). Flush surfaces any FK/enum error here and now.
        self._db.flush()
        self._mark_public_sites(action_type, entity_type, entity_id)

    def _mark_public_sites(self, action_type: str, entity_type: str | None, entity_id: uuid.UUID | None) -> None:
        """Every public-facing change is logged here, so this is the one place
        that tells the sites to rebuild."""
        builds = SqlAlchemySiteBuildRepository(self._db)
        builds.mark(sites_for_activity(action_type))
        if action_type == "project_updated" and entity_type == "project" and entity_id:
            status = self._db.scalar(select(Projects.status).where(Projects.id == entity_id))
            # Draft edits are invisible. Others save often, so they wait for a quiet period.
            if status is not None and status != ProjectStatus.DRAFT:
                builds.mark(("portfolio",), delay_seconds=QUIET_PERIOD_SECONDS)

    def list_recent(self, limit: int) -> list[ActivityEntry]:
        rows = self._db.scalars(
            select(ActivityLog).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit)
        ).all()

        existing: set[tuple[str, uuid.UUID]] = set()
        for entity_type, model in _ENTITY_MODELS.items():
            ids = {r.entity_id for r in rows if r.entity_type == entity_type and r.entity_id}
            if ids:
                found = self._db.scalars(select(model.id).where(model.id.in_(ids))).all()
                existing.update((entity_type, found_id) for found_id in found)

        return [
            ActivityEntry(
                id=r.id,
                action_type=r.action_type.value,
                description=r.description,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                entity_title=r.entity_title,
                performed_by=r.performed_by,
                created_at=r.created_at,
                entity_exists=(r.entity_type, r.entity_id) in existing,
            )
            for r in rows
        ]

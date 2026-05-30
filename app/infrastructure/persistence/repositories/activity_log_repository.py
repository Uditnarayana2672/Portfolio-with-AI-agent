"""SQLAlchemy implementation of ActivityLogRepository (infrastructure layer)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.infrastructure.persistence.orm.models import ActivityLog, ActivityType


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

"""SQLAlchemy implementation of PortfolioContentRepository (infrastructure layer)."""
from __future__ import annotations

import uuid

from sqlalchemy import select, update as sa_update
from sqlalchemy.orm import Session

from app.domain.entities.portfolio_content import PortfolioContent
from app.domain.repositories.portfolio_content_repository import PortfolioContentRepository
from app.infrastructure.persistence.orm.models import PortfolioContent as PortfolioContentRow
from app.infrastructure.persistence.orm.models import Users


class SqlAlchemyPortfolioContentRepository(PortfolioContentRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self) -> PortfolioContent | None:
        row = self._db.execute(
            select(
                PortfolioContentRow.content,
                PortfolioContentRow.version,
                PortfolioContentRow.updated_at,
                Users.name,
            ).outerjoin(Users, Users.id == PortfolioContentRow.updated_by)
        ).first()
        if row is None:
            return None
        return PortfolioContent(
            content=row.content,
            version=row.version,
            updated_at=row.updated_at,
            updated_by_name=row.name,
        )

    def update(
        self, *, expected_version: int, content: dict, updated_by: uuid.UUID
    ) -> PortfolioContent | None:
        # The version check lives in the WHERE clause so it is atomic.
        updated = self._db.execute(
            sa_update(PortfolioContentRow)
            .where(PortfolioContentRow.version == expected_version)
            .values(content=content, version=expected_version + 1, updated_by=updated_by)
            .returning(PortfolioContentRow.version)
        ).first()
        if updated is None:
            return None
        self._db.flush()
        return self.get()

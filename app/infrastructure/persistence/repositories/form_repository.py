"""SQLAlchemy implementation of FormRepository (infrastructure layer)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.form import Form
from app.domain.repositories.form_repository import FormRepository
from app.infrastructure.persistence.orm.models import Forms


class SqlAlchemyFormRepository(FormRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self, author_id: uuid.UUID, search: str | None) -> list[Form]:
        q = select(Forms).where(Forms.author_id == author_id)
        if search:
            q = q.where(Forms.name.ilike(f"%{search}%"))
        rows = (
            self._db.execute(q.order_by(Forms.created_at.desc())).scalars().all()
        )
        return [self._to_entity(row) for row in rows]

    def get(self, id: uuid.UUID) -> Form | None:
        row = (
            self._db.execute(select(Forms).where(Forms.id == id)).scalars().first()
        )
        if row is None:
            return None
        return self._to_entity(row)

    @staticmethod
    def _to_entity(row: Forms) -> Form:
        return Form(
            id=row.id,
            author_id=row.author_id,
            name=row.name,
            form_type=row.form_type,
            config=dict(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

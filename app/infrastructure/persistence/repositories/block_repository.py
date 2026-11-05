"""SQLAlchemy implementation of BlockRepository (infrastructure layer)."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete as sa_delete, func, select, update as sa_update
from sqlalchemy.orm import Session

from app.domain.entities.block import Block
from app.domain.repositories.block_repository import BlockRepository, NewBlock
from app.infrastructure.persistence.orm.models import ProjectBlocks


class SqlAlchemyBlockRepository(BlockRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_project(self, block_id: uuid.UUID, project_id: uuid.UUID) -> Block | None:
        row = (
            self._db.execute(
                select(ProjectBlocks).where(
                    ProjectBlocks.id == block_id,
                    ProjectBlocks.project_id == project_id,
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        return Block(
            id=row.id,
            project_id=row.project_id,
            block_type=row.block_type,
            position=row.position,
            config=dict(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def shift_positions_from(self, project_id: uuid.UUID, position: int) -> None:
        self._db.execute(
            sa_update(ProjectBlocks)
            .where(
                ProjectBlocks.project_id == project_id,
                ProjectBlocks.position >= position,
            )
            .values(
                position=ProjectBlocks.position + 1,
                updated_at=func.now(),
            )
        )
        self._db.flush()

    def add(self, new: NewBlock) -> Block:
        row = ProjectBlocks(
            project_id=new.project_id,
            block_type=new.block_type,
            position=new.position,
            config=new.config,
        )
        self._db.add(row)
        # Flush (not commit) so the DB assigns id/created_at while leaving the
        # request's transaction open — get_db commits once the request succeeds.
        self._db.flush()
        self._db.refresh(row)
        return Block(
            id=row.id,
            project_id=row.project_id,
            block_type=row.block_type,
            position=row.position,
            config=dict(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def update_block(
        self,
        block_id: uuid.UUID,
        *,
        config: dict | None = None,
        position: int | None = None,
    ) -> Block:
        row = self._db.get(ProjectBlocks, block_id)
        if row is None:
            raise RuntimeError(f"Block {block_id} vanished between load and update")
        if config is not None:
            row.config = config
        if position is not None:
            row.position = position
        # No onupdate on the column, so stamp updated_at explicitly (mirrors the
        # project repo). Concurrent writers: last flush wins, updated_at follows.
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        self._db.flush()
        self._db.refresh(row)
        return Block(
            id=row.id,
            project_id=row.project_id,
            block_type=row.block_type,
            position=row.position,
            config=dict(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def delete(self, block_id: uuid.UUID) -> None:
        self._db.execute(sa_delete(ProjectBlocks).where(ProjectBlocks.id == block_id))
        self._db.flush()

    def reorder(self, project_id: uuid.UUID, ordered_block_ids: list[uuid.UUID]) -> None:
        for position, block_id in enumerate(ordered_block_ids):
            self._db.execute(
                sa_update(ProjectBlocks)
                .where(
                    ProjectBlocks.id == block_id,
                    ProjectBlocks.project_id == project_id,
                )
                .values(
                    position=position,
                    updated_at=func.now(),
                )
            )
        self._db.flush()

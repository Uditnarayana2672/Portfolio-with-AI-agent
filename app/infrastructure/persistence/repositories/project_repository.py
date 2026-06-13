"""SQLAlchemy implementation of ProjectRepository (infrastructure layer)."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.entities.block import Block
from app.domain.entities.project import Project
from app.domain.repositories.project_repository import NewProject, ProjectRepository
from app.infrastructure.persistence.orm.models import (
    ContentVisibility,
    ProjectBlocks,
    ProjectStatus,
    Projects,
)


class SqlAlchemyProjectRepository(ProjectRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def slug_exists(self, slug: str) -> bool:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(Projects)
                .where(Projects.slug == slug)
            )
            or 0
        ) > 0

    def add(self, new: NewProject) -> Project:
        row = Projects(
            title=new.title,
            slug=new.slug,
            excerpt=new.excerpt,
            thumbnail_url=new.thumbnail_url,
            tech_stack=new.tech_stack,
            template_id=new.template_id,
            github_url=new.github_url,
            demo_url=new.demo_url,
            status=ProjectStatus(new.status),
            visibility=ContentVisibility(new.visibility),
            is_featured=new.is_featured,
            seo=new.seo,
            author_id=new.author_id,
        )
        self._db.add(row)
        # Flush (not commit) so the DB assigns id/created_at while leaving the
        # request's transaction open — get_db commits once the request succeeds.
        self._db.flush()
        self._db.refresh(row)
        return self._to_entity(row)

    def get_with_blocks(self, project_id: uuid.UUID) -> tuple[Project, list[Block]] | None:
        row = (
            self._db.execute(
                select(Projects)
                .where(Projects.id == project_id)
                .options(selectinload(Projects.project_blocks))
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        blocks = sorted(row.project_blocks, key=lambda b: b.position)
        return self._to_entity(row), [self._block_to_entity(b) for b in blocks]

    def delete(self, project_id: uuid.UUID) -> None:
        # The project_blocks FK has no ON DELETE CASCADE (see 001_initial_schema),
        # so delete the children first or the project delete violates the FK.
        self._db.execute(
            sa_delete(ProjectBlocks).where(ProjectBlocks.project_id == project_id)
        )
        self._db.execute(sa_delete(Projects).where(Projects.id == project_id))
        self._db.flush()

    def slug_exists_excluding(self, slug: str, exclude_id: uuid.UUID) -> bool:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(Projects)
                .where(Projects.slug == slug, Projects.id != exclude_id)
            )
            or 0
        ) > 0

    def count_featured_excluding(self, exclude_id: uuid.UUID) -> int:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(Projects)
                .where(Projects.is_featured.is_(True), Projects.id != exclude_id)
            )
            or 0
        )

    def update(self, project_id: uuid.UUID, changes: dict) -> tuple[Project, list[Block]]:
        row = (
            self._db.execute(
                select(Projects)
                .where(Projects.id == project_id)
                .options(selectinload(Projects.project_blocks))
            )
            .scalars()
            .first()
        )
        if row is None:
            raise RuntimeError(f"Project {project_id} vanished between load and update")

        blocks = sorted(row.project_blocks, key=lambda b: b.position)

        for key, value in changes.items():
            if key == "status":
                row.status = ProjectStatus(value)
            elif key == "visibility":
                row.visibility = ContentVisibility(value)
            elif key == "tech_stack":
                row.tech_stack = list(value)
            else:
                setattr(row, key, value)

        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        self._db.flush()
        self._db.refresh(row)
        return self._to_entity(row), [self._block_to_entity(b) for b in blocks]

    @staticmethod
    def _block_to_entity(row: ProjectBlocks) -> Block:
        return Block(
            id=row.id,
            project_id=row.project_id,
            block_type=row.block_type,
            position=row.position,
            config=dict(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _to_entity(row: Projects) -> Project:
        return Project(
            id=row.id,
            title=row.title,
            slug=row.slug,
            excerpt=row.excerpt,
            thumbnail_url=row.thumbnail_url,
            tech_stack=list(row.tech_stack or []),
            template_id=row.template_id,
            github_url=row.github_url,
            demo_url=row.demo_url,
            status=row.status.value,
            visibility=row.visibility.value,
            is_featured=row.is_featured,
            views=row.views,
            seo=dict(row.seo or {}),
            author_id=row.author_id,
            published_at=row.published_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

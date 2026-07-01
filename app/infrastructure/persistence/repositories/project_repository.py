"""SQLAlchemy implementation of ProjectRepository (infrastructure layer)."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import asc, delete as sa_delete, desc, func, select, update as sa_update
from sqlalchemy.orm import Session, selectinload

from app.domain.entities.block import Block
from app.domain.entities.project import Project
from app.domain.repositories.project_repository import NewProject, ProjectRepository
from app.infrastructure.persistence.orm.models import (
    ContentType,
    ContentVisibility,
    ProjectBlocks,
    ProjectStatus,
    Projects,
    ReactionType,
    Reactions,
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
            meta=new.meta,
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

    def get_published_by_slug(self, slug: str) -> tuple[Project, list[Block]] | None:
        row = (
            self._db.execute(
                select(Projects)
                .where(
                    Projects.slug == slug,
                    Projects.status == ProjectStatus.PUBLISHED,
                    Projects.visibility.in_(
                        [ContentVisibility.PUBLIC, ContentVisibility.UNLISTED]
                    ),
                )
                .options(selectinload(Projects.project_blocks))
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        blocks = sorted(row.project_blocks, key=lambda b: b.position)
        return self._to_entity(row), [self._block_to_entity(b) for b in blocks]

    def increment_views(self, project_id: uuid.UUID) -> int:
        new_total = self._db.scalar(
            sa_update(Projects)
            .where(Projects.id == project_id)
            .values(views=Projects.views + 1)
            .returning(Projects.views)
        )
        self._db.flush()
        return new_total or 0

    def list_published_brief(self) -> list[Project]:
        rows = (
            self._db.execute(
                select(Projects)
                .where(
                    Projects.status == ProjectStatus.PUBLISHED,
                    Projects.visibility == ContentVisibility.PUBLIC,
                )
                .order_by(desc(Projects.published_at))
            )
            .scalars()
            .all()
        )
        return [self._to_entity(row) for row in rows]

    def get_reaction_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        rows = self._db.execute(
            select(Reactions.reaction_type, func.count().label("cnt"))
            .where(
                Reactions.content_type == ContentType.PROJECT,
                Reactions.content_id == project_id,
            )
            .group_by(Reactions.reaction_type)
        ).all()
        return {row.reaction_type.value: row.cnt for row in rows}

    def add_reaction(
        self, project_id: uuid.UUID, reaction_type: str, session_id: str | None
    ) -> dict[str, int]:
        self._db.add(
            Reactions(
                content_type=ContentType.PROJECT,
                content_id=project_id,
                reaction_type=ReactionType(reaction_type),
                session_id=session_id,
            )
        )
        self._db.flush()
        return self.get_reaction_counts(project_id)

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

    def publish(self, project_id: uuid.UUID) -> Project:
        row = (
            self._db.execute(select(Projects).where(Projects.id == project_id))
            .scalars()
            .first()
        )
        if row is None:
            raise RuntimeError(f"Project {project_id} vanished between load and publish")

        now = datetime.datetime.now(datetime.timezone.utc)
        row.status = ProjectStatus.PUBLISHED
        row.published_at = now
        row.updated_at = now
        self._db.flush()
        self._db.refresh(row)
        return self._to_entity(row)

    def list_projects(
        self,
        author_id: uuid.UUID,
        status_filter: str | None,
        search: str | None,
        page: int,
        page_size: int,
        template_id: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> tuple[list[Project], list[int], int]:
        conditions = [Projects.author_id == author_id]

        if status_filter is not None:
            conditions.append(Projects.status == ProjectStatus(status_filter))

        if search:
            conditions.append(Projects.title.ilike(f"%{search}%"))

        if template_id is not None:
            conditions.append(Projects.template_id == template_id)

        total = (
            self._db.scalar(
                select(func.count()).select_from(Projects).where(*conditions)
            )
            or 0
        )

        sort_col = {
            "title": Projects.title,
            "created_at": Projects.created_at,
            "updated_at": Projects.updated_at,
            "views": Projects.views,
            "status": Projects.status,
        }.get(sort_by, Projects.created_at)
        order_fn = desc if sort_dir.lower() == "desc" else asc

        offset = (page - 1) * page_size
        rows = (
            self._db.execute(
                select(Projects)
                .where(*conditions)
                .order_by(order_fn(sort_col))
                .offset(offset)
                .limit(page_size)
            )
            .scalars()
            .all()
        )

        project_ids = [row.id for row in rows]
        reaction_counts_map: dict[uuid.UUID, int] = {}
        if project_ids:
            reaction_rows = self._db.execute(
                select(Reactions.content_id, func.count().label("cnt"))
                .where(
                    Reactions.content_type == ContentType.PROJECT,
                    Reactions.content_id.in_(project_ids),
                )
                .group_by(Reactions.content_id)
            ).all()
            reaction_counts_map = {row.content_id: row.cnt for row in reaction_rows}

        projects = [self._to_entity(row) for row in rows]
        reactions_counts = [reaction_counts_map.get(p.id, 0) for p in projects]

        return projects, reactions_counts, total

    def get_status_counts(self, author_id: uuid.UUID) -> dict[str, int]:
        rows = self._db.execute(
            select(Projects.status, func.count().label("cnt"))
            .where(Projects.author_id == author_id)
            .group_by(Projects.status)
        ).all()
        return {row.status.value: row.cnt for row in rows}

    def bulk_update_status(
        self, project_ids: list[uuid.UUID], status: str, author_id: uuid.UUID
    ) -> list[uuid.UUID]:
        now = datetime.datetime.now(datetime.timezone.utc)
        result = self._db.execute(
            sa_update(Projects)
            .where(Projects.id.in_(project_ids), Projects.author_id == author_id)
            .values(status=ProjectStatus(status), updated_at=now)
            .returning(Projects.id)
        )
        self._db.flush()
        return [row[0] for row in result]

    def bulk_delete(
        self, project_ids: list[uuid.UUID], author_id: uuid.UUID
    ) -> list[uuid.UUID]:
        # Confirm ownership and collect IDs that will actually be deleted.
        owned = self.get_owned_ids(project_ids, author_id)
        if not owned:
            return []
        self._db.execute(
            sa_delete(ProjectBlocks).where(ProjectBlocks.project_id.in_(owned))
        )
        self._db.execute(
            sa_delete(Projects).where(Projects.id.in_(owned))
        )
        self._db.flush()
        return owned

    def bulk_set_featured(
        self, project_ids: list[uuid.UUID], is_featured: bool, author_id: uuid.UUID
    ) -> list[uuid.UUID]:
        now = datetime.datetime.now(datetime.timezone.utc)
        result = self._db.execute(
            sa_update(Projects)
            .where(Projects.id.in_(project_ids), Projects.author_id == author_id)
            .values(is_featured=is_featured, updated_at=now)
            .returning(Projects.id)
        )
        self._db.flush()
        return [row[0] for row in result]

    def get_owned_ids(
        self, project_ids: list[uuid.UUID], author_id: uuid.UUID
    ) -> list[uuid.UUID]:
        rows = self._db.execute(
            select(Projects.id).where(
                Projects.id.in_(project_ids),
                Projects.author_id == author_id,
            )
        ).all()
        return [row[0] for row in rows]

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
            meta=dict(row.meta or {}),
            author_id=row.author_id,
            published_at=row.published_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

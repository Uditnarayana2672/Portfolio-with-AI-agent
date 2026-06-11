"""SQLAlchemy implementation of ProjectRepository (infrastructure layer)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities.project import Project
from app.domain.repositories.project_repository import NewProject, ProjectRepository
from app.infrastructure.persistence.orm.models import (
    ContentVisibility,
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

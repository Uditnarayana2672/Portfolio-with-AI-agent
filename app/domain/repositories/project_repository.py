"""ProjectRepository port (domain layer).

Abstract contract for persisting/querying projects. The application layer
depends on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities.block import Block
from app.domain.entities.project import Project


@dataclass(frozen=True)
class NewProject:
    """The fields needed to persist a freshly created draft project. Distinct
    from the ``Project`` entity, which also carries server-assigned id/timestamps."""

    title: str
    slug: str
    tech_stack: list[str]
    template_id: str
    status: str
    visibility: str
    is_featured: bool
    seo: dict
    author_id: uuid.UUID
    excerpt: str | None = None
    github_url: str | None = None
    demo_url: str | None = None


class ProjectRepository(ABC):
    @abstractmethod
    def slug_exists(self, slug: str) -> bool:
        """True if a project already owns this slug. Drives collision avoidance."""

    @abstractmethod
    def add(self, new: NewProject) -> Project:
        """Persist a new project and return it with server-assigned id/timestamps.
        Flushes so the id is available; the request's session owns the commit."""

    @abstractmethod
    def get_with_blocks(self, project_id: uuid.UUID) -> tuple[Project, list[Block]] | None:
        """Return (project, blocks ordered by position) or None if not found."""

    @abstractmethod
    def slug_exists_excluding(self, slug: str, exclude_id: uuid.UUID) -> bool:
        """True if a *different* project already owns this slug. Used during update
        so the project's own current slug does not trigger a false collision."""

    @abstractmethod
    def update(self, project_id: uuid.UUID, changes: dict) -> tuple[Project, list[Block]]:
        """Apply a partial update to an existing project.

        ``changes`` maps column names to new values. ``seo`` (if present) has
        already been merged with the existing value by the use case. Returns
        (updated_project, blocks_ordered_by_position). Callers must confirm the
        row exists before calling. Flushes; the request session commits.
        """

    @abstractmethod
    def delete(self, project_id: uuid.UUID) -> None:
        """Permanently delete a project and all of its child blocks. The FK on
        project_blocks has no ON DELETE CASCADE, so the implementation must
        remove the blocks explicitly (in the same transaction) before the project.
        Callers must confirm the row exists before calling. Flushes; the request
        session commits."""

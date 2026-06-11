"""ProjectRepository port (domain layer).

Abstract contract for persisting/querying projects. The application layer
depends on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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

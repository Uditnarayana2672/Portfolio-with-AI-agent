"""BlogCategoryRepository port (domain layer)."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.domain.entities.blog_post import BlogCategory


class BlogCategoryRepository(ABC):
    @abstractmethod
    def list_with_counts(self) -> list[BlogCategory]:
        """All categories ordered by sort_order then name, with post counts."""

    @abstractmethod
    def get(self, category_id: uuid.UUID) -> BlogCategory | None: ...

    @abstractmethod
    def find_by_name_or_slug(self, name: str, slug: str) -> BlogCategory | None:
        """Case-insensitive name match, or exact slug match."""

    @abstractmethod
    def add(self, *, name: str, slug: str, description: str | None) -> BlogCategory:
        """Insert at the end of the sort order."""

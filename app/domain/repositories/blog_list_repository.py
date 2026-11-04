"""BlogListRepository port (domain layer).

The read side of the Blog Manager: the filtered, searched, paged post list,
its facet counts and the stats cards. Kept apart from BlogPostRepository (the
editor's aggregate) so list queries can grow without touching the editor's
contract. Writes (archive, delete, restore) go through BlogPostRepository.
"""
from __future__ import annotations

import datetime
import uuid
from abc import ABC, abstractmethod

from app.domain.entities.blog_post import BlogStatusStats, PostListQuery, PostListRow


class BlogListRepository(ABC):
    @abstractmethod
    def list_posts(self, query: PostListQuery) -> tuple[list[PostListRow], int]:
        """One page of rows and the total matching ``query``."""

    @abstractmethod
    def facet_counts(self, query: PostListQuery) -> tuple[dict[str, int], dict[str, int]]:
        """(counts by status, counts by category id or "none").

        Cross-filtered: status counts apply the category and search but not
        the status filter; category counts apply status and search but not
        the category filter.
        """

    @abstractmethod
    def status_stats(self, author_id: uuid.UUID, created_since: datetime.datetime) -> BlogStatusStats:
        """Counts by status, posts created since a moment, next scheduled time,
        and drafts whose scheduled publish failed."""

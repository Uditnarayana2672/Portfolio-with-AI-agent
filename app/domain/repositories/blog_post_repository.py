"""BlogPostRepository port (domain layer).

Abstract contract for the blog post aggregate: the working copy row, its
revisions, slug redirects, and the read-only lookups the editor needs (media,
authors, tags, link targets). The SQLAlchemy implementation lives in
infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.domain.entities.blog_post import (
    AuthorInfo,
    BlogMedia,
    BlogPost,
    BlogRevision,
    LinkTarget,
)


class BlogPostRepository(ABC):
    # ── working copy ──────────────────────────────────────────────────────

    @abstractmethod
    def get(self, post_id: uuid.UUID, *, for_update: bool = False) -> BlogPost | None:
        """Load a post; ``for_update`` takes a row lock (publish, scheduler)."""

    @abstractmethod
    def add(self, fields: dict) -> BlogPost:
        """Insert a new post from column values; returns it with version 1."""

    @abstractmethod
    def update(self, post_id: uuid.UUID, expected_version: int | None, fields: dict) -> BlogPost:
        """Apply column changes and bump ``version``.

        With ``expected_version`` the write only succeeds if the row still has
        that version; otherwise raises ``VersionConflictError``. ``None`` skips
        the check (scheduler, internal follow-up writes).
        """

    @abstractmethod
    def delete(self, post_id: uuid.UUID) -> None:
        """Hard-delete the post (revisions and redirects cascade)."""

    @abstractmethod
    def slug_owner(self, slug: str) -> uuid.UUID | None:
        """Id of the post currently using ``slug``, if any."""

    @abstractmethod
    def redirect_owner(self, slug: str) -> uuid.UUID | None:
        """Id of the post an old ``slug`` redirects to, if any."""

    @abstractmethod
    def add_redirect(self, old_slug: str, post_id: uuid.UUID) -> None:
        """Record (or re-point) a 301 from ``old_slug`` to the post."""

    @abstractmethod
    def delete_redirect(self, slug: str) -> None:
        """Remove a redirect row (the post took its old slug back)."""

    @abstractmethod
    def due_scheduled_ids(self, limit: int) -> list[uuid.UUID]:
        """Ids of scheduled posts whose time has come, locked with SKIP LOCKED."""

    # ── revisions ─────────────────────────────────────────────────────────

    @abstractmethod
    def add_revision(
        self,
        *,
        post_id: uuid.UUID,
        kind: str,
        label: str | None,
        snapshot: dict,
        content_html: str,
        content_hash: str,
        word_count: int,
        created_by: uuid.UUID | None,
    ) -> BlogRevision: ...

    @abstractmethod
    def get_revision(self, post_id: uuid.UUID, revision_id: uuid.UUID) -> BlogRevision | None: ...

    @abstractmethod
    def latest_revision(self, post_id: uuid.UUID) -> BlogRevision | None: ...

    @abstractmethod
    def list_revisions(
        self, post_id: uuid.UUID, *, kind: str | None, page: int, limit: int
    ) -> tuple[list[BlogRevision], int]:
        """Newest first; returns (page of revisions, total)."""

    @abstractmethod
    def prune_revisions(self, post_id: uuid.UUID, keep: int, protect: uuid.UUID | None) -> None:
        """Keep the newest ``keep`` manual/restore revisions; publish revisions
        and ``protect`` (the live one) are never pruned."""

    # ── lookups ───────────────────────────────────────────────────────────

    @abstractmethod
    def get_media(self, asset_ids: list[uuid.UUID]) -> dict[uuid.UUID, BlogMedia]:
        """Existing assets among ``asset_ids`` (missing ids are absent)."""

    @abstractmethod
    def get_author(self, user_id: uuid.UUID) -> AuthorInfo | None: ...

    @abstractmethod
    def category_exists(self, category_id: uuid.UUID) -> bool: ...

    @abstractmethod
    def list_tags(self, prefix: str, limit: int) -> list[tuple[str, int]]:
        """(tag, use count) across non-archived posts, most used first."""

    @abstractmethod
    def search_link_targets(self, query: str, limit: int) -> list[LinkTarget]:
        """Posts and projects whose title matches ``query``."""

    @abstractmethod
    def link_target_status(self, kind: str, target_id: uuid.UUID) -> tuple[str, str] | None:
        """(status, public url) for an internal link target, or None if gone."""

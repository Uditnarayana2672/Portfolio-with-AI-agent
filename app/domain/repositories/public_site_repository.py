"""PublicSiteRepository port: everything anonymous visitors read and write."""
from __future__ import annotations

import datetime
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities.blog_post import BlogPost
from app.domain.entities.project import Project


@dataclass(frozen=True)
class PublicComment:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    author_name: str
    is_author: bool
    content: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class PollBlock:
    block_id: uuid.UUID
    config: dict


@dataclass(frozen=True)
class Subscriber:
    id: uuid.UUID
    email: str
    status: str
    confirm_expires_at: datetime.datetime | None


class PublicSiteRepository(ABC):
    # projects
    @abstractmethod
    def list_public_projects(self) -> list[tuple[Project, str | None]]:
        """Published public projects, each with its first hero image if any."""

    @abstractmethod
    def project_slugs(self) -> list[str]:
        """Every page that must exist: published public and unlisted projects."""

    @abstractmethod
    def project_id_by_slug(self, slug: str) -> uuid.UUID | None: ...

    @abstractmethod
    def project_views(self, project_id: uuid.UUID) -> int: ...

    # blog
    @abstractmethod
    def live_blog_posts(self) -> list[tuple[BlogPost, dict]]:
        """Published public posts with their live revision snapshot, newest first."""

    @abstractmethod
    def search_blog_ids(self, query: str) -> set[uuid.UUID]: ...

    @abstractmethod
    def blog_categories(self) -> list[tuple[uuid.UUID, str, str, str | None]]:
        """(id, name, slug, description) by sort order."""

    @abstractmethod
    def blog_redirects(self) -> list[tuple[str, uuid.UUID]]: ...

    @abstractmethod
    def blog_views(self, post_id: uuid.UUID) -> int: ...

    @abstractmethod
    def blog_id_by_old_slug(self, slug: str) -> uuid.UUID | None: ...

    # engagement
    @abstractmethod
    def record_view(self, kind: str, content_id: uuid.UUID, path: str, session_id: str | None) -> bool:
        """Count a view unless this session already did within 30 minutes."""

    @abstractmethod
    def reaction_counts(self, kind: str, content_id: uuid.UUID) -> dict[str, int]: ...

    @abstractmethod
    def add_reaction(self, kind: str, content_id: uuid.UUID, reaction: str, session_id: str | None) -> None: ...

    # polls
    @abstractmethod
    def public_poll_block(self, block_id: uuid.UUID) -> PollBlock | None: ...

    @abstractmethod
    def current_poll_id(self, block: PollBlock) -> uuid.UUID | None:
        """The poll row for a block, only if its question and options still match. Never writes."""

    @abstractmethod
    def ensure_poll(self, block: PollBlock) -> uuid.UUID:
        """The poll row for a block. A changed question or options resets votes."""

    @abstractmethod
    def poll_tallies(self, poll_id: uuid.UUID) -> dict[int, int]: ...

    @abstractmethod
    def poll_vote_of(self, poll_id: uuid.UUID, session_id: str) -> int | None: ...

    @abstractmethod
    def add_poll_vote(self, poll_id: uuid.UUID, option_index: int, session_id: str) -> bool:
        """False when this session has already voted."""

    # comments
    @abstractmethod
    def approved_comments(self, post_id: uuid.UUID) -> list[PublicComment]: ...

    @abstractmethod
    def comment_post_id(self, comment_id: uuid.UUID) -> uuid.UUID | None: ...

    @abstractmethod
    def add_comment(
        self, *, post_id: uuid.UUID, parent_id: uuid.UUID | None, name: str, email: str | None, content: str
    ) -> None: ...

    # contact
    @abstractmethod
    def add_contact_message(self, *, name: str, email: str, subject: str, message: str) -> None: ...

    # newsletter
    @abstractmethod
    def subscriber_by_email(self, email: str) -> Subscriber | None: ...

    @abstractmethod
    def save_pending_subscriber(self, email: str, token: str, expires_at: datetime.datetime) -> None: ...

    @abstractmethod
    def subscriber_by_confirm_token(self, token: str) -> Subscriber | None: ...

    @abstractmethod
    def activate_subscriber(self, subscriber_id: uuid.UUID, now: datetime.datetime) -> None: ...

    @abstractmethod
    def unsubscribe(self, token: str, now: datetime.datetime) -> bool: ...

    @abstractmethod
    def unsubscribe_token_of(self, email: str) -> str | None: ...

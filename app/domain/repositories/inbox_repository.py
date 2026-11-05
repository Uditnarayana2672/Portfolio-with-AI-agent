"""InboxRepository port: what the admin moderates and reads."""
from __future__ import annotations

import datetime
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AdminComment:
    id: uuid.UUID
    post_id: uuid.UUID
    post_title: str
    post_slug: str
    author_name: str
    author_email: str | None
    content: str
    status: str
    parent_id: uuid.UUID | None
    created_at: datetime.datetime


@dataclass(frozen=True)
class AdminMessage:
    id: uuid.UUID
    name: str
    email: str
    subject: str
    message: str
    read: bool
    created_at: datetime.datetime


@dataclass(frozen=True)
class AdminSubscriber:
    id: uuid.UUID
    email: str
    status: str
    subscribed_at: datetime.datetime
    confirmed_at: datetime.datetime | None


@dataclass(frozen=True)
class Recipient:
    email: str
    unsubscribe_token: str | None


class InboxRepository(ABC):
    @abstractmethod
    def counts(self) -> dict[str, int]: ...

    @abstractmethod
    def list_comments(self, status: str, limit: int, offset: int) -> tuple[list[AdminComment], int]: ...

    @abstractmethod
    def get_comment(self, comment_id: uuid.UUID) -> AdminComment | None: ...

    @abstractmethod
    def set_comment_approved(self, comment_id: uuid.UUID, approved: bool) -> AdminComment | None: ...

    @abstractmethod
    def delete_comment(self, comment_id: uuid.UUID) -> bool: ...

    @abstractmethod
    def add_author_reply(
        self, *, post_id: uuid.UUID, parent_id: uuid.UUID, author_id: uuid.UUID, author_name: str, content: str
    ) -> AdminComment: ...

    @abstractmethod
    def list_messages(self, status: str, limit: int, offset: int) -> tuple[list[AdminMessage], int]: ...

    @abstractmethod
    def set_message_read(self, message_id: uuid.UUID, read: bool) -> AdminMessage | None: ...

    @abstractmethod
    def delete_message(self, message_id: uuid.UUID) -> bool: ...

    @abstractmethod
    def list_subscribers(self, status: str, limit: int, offset: int) -> tuple[list[AdminSubscriber], int]: ...

    @abstractmethod
    def delete_subscriber(self, subscriber_id: uuid.UUID) -> bool: ...

    @abstractmethod
    def active_recipients(self) -> list[Recipient]: ...

    @abstractmethod
    def newsletter_already_sent(self, post_id: uuid.UUID) -> bool: ...

    @abstractmethod
    def record_newsletter_send(self, post_id: uuid.UUID, recipients: int) -> None: ...

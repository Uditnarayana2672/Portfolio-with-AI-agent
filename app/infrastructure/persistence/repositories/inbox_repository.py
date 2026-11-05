"""SQLAlchemy implementation of InboxRepository (infrastructure layer)."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from app.domain.repositories.inbox_repository import (
    AdminComment,
    AdminMessage,
    AdminSubscriber,
    InboxRepository,
    Recipient,
)
from app.infrastructure.persistence.orm.models import (
    BlogPosts,
    Comments,
    ContactMessages,
    NewsletterSends,
    NewsletterSubscribers,
    SubscriberStatus,
)


class SqlAlchemyInboxRepository(InboxRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def counts(self) -> dict[str, int]:
        def count(*where, model) -> int:
            return self._db.scalar(select(func.count()).select_from(model).where(*where)) or 0

        return {
            "comments_pending": count(Comments.is_approved.is_(False), model=Comments),
            "messages_unread": count(ContactMessages.read.is_(False), model=ContactMessages),
            "subscribers_confirmed": count(
                NewsletterSubscribers.status == SubscriberStatus.ACTIVE, model=NewsletterSubscribers
            ),
        }

    # ── comments ─────────────────────────────────────────────────────────

    @staticmethod
    def _comment(row: Comments, title: str, slug: str) -> AdminComment:
        return AdminComment(
            id=row.id, post_id=row.blog_id, post_title=title, post_slug=slug,
            author_name=row.author_name or "Guest", author_email=row.author_email, content=row.content,
            status="approved" if row.is_approved else "pending", parent_id=row.parent_id, created_at=row.created_at,
        )

    def list_comments(self, status: str, limit: int, offset: int) -> tuple[list[AdminComment], int]:
        where = []
        if status != "all":
            where.append(Comments.is_approved.is_(status == "approved"))
        total = self._db.scalar(select(func.count()).select_from(Comments).where(*where)) or 0
        rows = self._db.execute(
            select(Comments, BlogPosts.title, BlogPosts.slug)
            .join(BlogPosts, BlogPosts.id == Comments.blog_id)
            .where(*where)
            .order_by(Comments.created_at.desc())
            .limit(limit).offset(offset)
        ).all()
        return [self._comment(c, title, slug) for c, title, slug in rows], total

    def get_comment(self, comment_id: uuid.UUID) -> AdminComment | None:
        row = self._db.execute(
            select(Comments, BlogPosts.title, BlogPosts.slug)
            .join(BlogPosts, BlogPosts.id == Comments.blog_id)
            .where(Comments.id == comment_id)
        ).first()
        return self._comment(*row) if row else None

    def set_comment_approved(self, comment_id: uuid.UUID, approved: bool) -> AdminComment | None:
        row = self._db.get(Comments, comment_id)
        if row is None:
            return None
        row.is_approved = approved
        self._db.flush()
        return self.get_comment(comment_id)

    def delete_comment(self, comment_id: uuid.UUID) -> bool:
        self._db.execute(sa_delete(Comments).where(Comments.parent_id == comment_id))
        return self._db.execute(sa_delete(Comments).where(Comments.id == comment_id)).rowcount > 0

    def add_author_reply(
        self, *, post_id: uuid.UUID, parent_id: uuid.UUID, author_id: uuid.UUID, author_name: str, content: str
    ) -> AdminComment:
        row = Comments(
            blog_id=post_id, parent_id=parent_id, user_id=author_id, author_name=author_name,
            content=content, is_approved=True,
        )
        self._db.add(row)
        self._db.flush()
        return self.get_comment(row.id)

    # ── messages ─────────────────────────────────────────────────────────

    @staticmethod
    def _message(row: ContactMessages) -> AdminMessage:
        return AdminMessage(row.id, row.name, row.email, row.subject, row.message, row.read, row.created_at)

    def list_messages(self, status: str, limit: int, offset: int) -> tuple[list[AdminMessage], int]:
        where = [] if status == "all" else [ContactMessages.read.is_(status == "read")]
        total = self._db.scalar(select(func.count()).select_from(ContactMessages).where(*where)) or 0
        rows = self._db.scalars(
            select(ContactMessages).where(*where).order_by(ContactMessages.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return [self._message(r) for r in rows], total

    def set_message_read(self, message_id: uuid.UUID, read: bool) -> AdminMessage | None:
        row = self._db.get(ContactMessages, message_id)
        if row is None:
            return None
        row.read = read
        row.read_at = datetime.datetime.now(datetime.timezone.utc) if read else None
        self._db.flush()
        return self._message(row)

    def delete_message(self, message_id: uuid.UUID) -> bool:
        return self._db.execute(sa_delete(ContactMessages).where(ContactMessages.id == message_id)).rowcount > 0

    # ── subscribers ──────────────────────────────────────────────────────

    def list_subscribers(self, status: str, limit: int, offset: int) -> tuple[list[AdminSubscriber], int]:
        where = [] if status == "all" else [NewsletterSubscribers.status == SubscriberStatus(status)]
        total = self._db.scalar(select(func.count()).select_from(NewsletterSubscribers).where(*where)) or 0
        rows = self._db.scalars(
            select(NewsletterSubscribers).where(*where)
            .order_by(NewsletterSubscribers.subscribed_at.desc()).limit(limit).offset(offset)
        ).all()
        return [AdminSubscriber(r.id, r.email, r.status.value, r.subscribed_at, r.confirmed_at) for r in rows], total

    def delete_subscriber(self, subscriber_id: uuid.UUID) -> bool:
        return self._db.execute(
            sa_delete(NewsletterSubscribers).where(NewsletterSubscribers.id == subscriber_id)
        ).rowcount > 0

    def active_recipients(self) -> list[Recipient]:
        rows = self._db.execute(
            select(NewsletterSubscribers.email, NewsletterSubscribers.unsubscribe_token)
            .where(NewsletterSubscribers.status == SubscriberStatus.ACTIVE)
        ).all()
        return [Recipient(email, token) for email, token in rows]

    def newsletter_already_sent(self, post_id: uuid.UUID) -> bool:
        return self._db.get(NewsletterSends, post_id) is not None

    def record_newsletter_send(self, post_id: uuid.UUID, recipients: int) -> None:
        self._db.add(NewsletterSends(post_id=post_id, recipients=recipients))
        self._db.flush()

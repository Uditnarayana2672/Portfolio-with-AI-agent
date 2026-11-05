"""SQLAlchemy implementation of PublicSiteRepository (infrastructure layer)."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete as sa_delete, func, select, update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.entities.blog_post import BlogPost
from app.domain.entities.project import Project
from app.domain.repositories.public_site_repository import (
    PollBlock,
    PublicComment,
    PublicSiteRepository,
    Subscriber,
)
from app.infrastructure.persistence.orm.models import (
    BlogCategories,
    BlogPostRevisions,
    BlogPosts,
    BlogSlugRedirects,
    BlogStatus,
    Comments,
    ContactMessages,
    ContentType,
    ContentVisibility,
    NewsletterSubscribers,
    PageViews,
    PollVotes,
    Polls,
    ProjectBlocks,
    ProjectStatus,
    Projects,
    ReactionType,
    Reactions,
    SubscriberStatus,
)
from app.infrastructure.persistence.repositories.blog_post_repository import SqlAlchemyBlogPostRepository
from app.infrastructure.persistence.repositories.project_repository import SqlAlchemyProjectRepository

VIEW_DEDUPE = datetime.timedelta(minutes=30)
_CONTENT_TYPES = {"project": ContentType.PROJECT, "blog": ContentType.BLOG_POST}


class SqlAlchemyPublicSiteRepository(PublicSiteRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    # ── projects ─────────────────────────────────────────────────────────

    def list_public_projects(self) -> list[tuple[Project, str | None]]:
        rows = self._db.scalars(
            select(Projects)
            .where(Projects.status == ProjectStatus.PUBLISHED, Projects.visibility == ContentVisibility.PUBLIC)
            .order_by(Projects.published_at.desc().nulls_last(), Projects.created_at.desc())
        ).all()
        heroes: dict[uuid.UUID, str] = {}
        if rows:
            blocks = self._db.execute(
                select(ProjectBlocks.project_id, ProjectBlocks.config)
                .where(ProjectBlocks.project_id.in_([r.id for r in rows]), ProjectBlocks.block_type == "hero")
                .order_by(ProjectBlocks.position)
            ).all()
            for project_id, config in blocks:
                url = (config or {}).get("background_image_url")
                if url and project_id not in heroes:
                    heroes[project_id] = url
        return [(SqlAlchemyProjectRepository._to_entity(r), heroes.get(r.id)) for r in rows]

    def project_slugs(self) -> list[str]:
        return list(self._db.scalars(
            select(Projects.slug).where(
                Projects.status == ProjectStatus.PUBLISHED,
                Projects.visibility.in_([ContentVisibility.PUBLIC, ContentVisibility.UNLISTED]),
            )
        ).all())

    def project_id_by_slug(self, slug: str) -> uuid.UUID | None:
        return self._db.scalar(
            select(Projects.id).where(
                Projects.slug == slug,
                Projects.status == ProjectStatus.PUBLISHED,
                Projects.visibility.in_([ContentVisibility.PUBLIC, ContentVisibility.UNLISTED]),
            )
        )

    def project_views(self, project_id: uuid.UUID) -> int:
        return self._db.scalar(select(Projects.views).where(Projects.id == project_id)) or 0

    # ── blog ─────────────────────────────────────────────────────────────

    def live_blog_posts(self) -> list[tuple[BlogPost, dict]]:
        rows = self._db.execute(
            select(BlogPosts, BlogPostRevisions.snapshot)
            .join(BlogPostRevisions, BlogPostRevisions.id == BlogPosts.published_revision_id)
            .where(BlogPosts.status == BlogStatus.PUBLISHED, BlogPosts.visibility == ContentVisibility.PUBLIC)
            .order_by(BlogPosts.published_at.desc().nulls_last())
        ).all()
        return [(SqlAlchemyBlogPostRepository._to_entity(post), snapshot) for post, snapshot in rows]

    def search_blog_ids(self, query: str) -> set[uuid.UUID]:
        tsquery = func.websearch_to_tsquery("english", query)
        vector = func.to_tsvector(
            "english",
            func.coalesce(BlogPosts.title, "") + " " + func.coalesce(BlogPosts.excerpt, "") + " "
            + func.coalesce(BlogPosts.content_text, ""),
        )
        title_hit = BlogPosts.title.ilike(f"%{query.replace('%', '').replace('_', '')}%")
        return set(self._db.scalars(
            select(BlogPosts.id).where(BlogPosts.status == BlogStatus.PUBLISHED, vector.op("@@")(tsquery) | title_hit)
        ).all())

    def blog_categories(self) -> list[tuple[uuid.UUID, str, str, str | None]]:
        rows = self._db.scalars(select(BlogCategories).order_by(BlogCategories.sort_order, BlogCategories.name)).all()
        return [(r.id, r.name, r.slug, r.description) for r in rows]

    def blog_redirects(self) -> list[tuple[str, uuid.UUID]]:
        rows = self._db.execute(select(BlogSlugRedirects.old_slug, BlogSlugRedirects.post_id)).all()
        return [(old, post_id) for old, post_id in rows]

    def blog_views(self, post_id: uuid.UUID) -> int:
        return self._db.scalar(select(BlogPosts.views).where(BlogPosts.id == post_id)) or 0

    def blog_id_by_old_slug(self, slug: str) -> uuid.UUID | None:
        return self._db.scalar(select(BlogSlugRedirects.post_id).where(BlogSlugRedirects.old_slug == slug))

    # ── engagement ───────────────────────────────────────────────────────

    def record_view(self, kind: str, content_id: uuid.UUID, path: str, session_id: str | None) -> bool:
        if session_id:
            since = datetime.datetime.now(datetime.timezone.utc) - VIEW_DEDUPE
            seen = self._db.scalar(
                select(PageViews.id)
                .where(PageViews.path == path, PageViews.session_id == session_id, PageViews.viewed_at >= since)
                .limit(1)
            )
            if seen:
                return False
        self._db.add(PageViews(path=path, session_id=session_id))
        model = Projects if kind == "project" else BlogPosts
        self._db.execute(
            sa_update(model).where(model.id == content_id).values(views=model.views + 1)
            .execution_options(synchronize_session=False)
        )
        self._db.flush()
        return True

    def reaction_counts(self, kind: str, content_id: uuid.UUID) -> dict[str, int]:
        rows = self._db.execute(
            select(Reactions.reaction_type, func.count())
            .where(Reactions.content_type == _CONTENT_TYPES[kind], Reactions.content_id == content_id)
            .group_by(Reactions.reaction_type)
        ).all()
        return {reaction.value: count for reaction, count in rows}

    def add_reaction(self, kind: str, content_id: uuid.UUID, reaction: str, session_id: str | None) -> None:
        self._db.add(Reactions(
            content_type=_CONTENT_TYPES[kind], content_id=content_id,
            reaction_type=ReactionType(reaction), session_id=session_id,
        ))
        self._db.flush()

    # ── polls ────────────────────────────────────────────────────────────

    def public_poll_block(self, block_id: uuid.UUID) -> PollBlock | None:
        config = self._db.scalar(
            select(ProjectBlocks.config)
            .join(Projects, Projects.id == ProjectBlocks.project_id)
            .where(
                ProjectBlocks.id == block_id,
                ProjectBlocks.block_type == "poll",
                Projects.status == ProjectStatus.PUBLISHED,
                Projects.visibility.in_([ContentVisibility.PUBLIC, ContentVisibility.UNLISTED]),
            )
        )
        return PollBlock(block_id, config) if config is not None else None

    def current_poll_id(self, block: PollBlock) -> uuid.UUID | None:
        poll = self._db.scalar(select(Polls).where(Polls.block_id == block.block_id))
        if poll is None:
            return None
        options = [str(o) for o in block.config.get("options") or []]
        same = poll.options == options and poll.question == str(block.config.get("question") or "")
        return poll.id if same else None

    def ensure_poll(self, block: PollBlock) -> uuid.UUID:
        options = [str(o) for o in block.config.get("options") or []]
        question = str(block.config.get("question") or "")
        poll = self._db.scalar(select(Polls).where(Polls.block_id == block.block_id))
        if poll is None:
            poll = Polls(question=question, options=options, anonymous=True, block_id=block.block_id)
            self._db.add(poll)
            self._db.flush()
        elif poll.options != options or poll.question != question:
            # Votes are stored by option position, so changed options can't keep them.
            self._db.execute(sa_delete(PollVotes).where(PollVotes.poll_id == poll.id))
            poll.options = options
            poll.question = question
            self._db.flush()
        return poll.id

    def poll_tallies(self, poll_id: uuid.UUID) -> dict[int, int]:
        rows = self._db.execute(
            select(PollVotes.option_index, func.count()).where(PollVotes.poll_id == poll_id).group_by(PollVotes.option_index)
        ).all()
        return {index: count for index, count in rows}

    def poll_vote_of(self, poll_id: uuid.UUID, session_id: str) -> int | None:
        return self._db.scalar(
            select(PollVotes.option_index).where(PollVotes.poll_id == poll_id, PollVotes.session_id == session_id)
        )

    def add_poll_vote(self, poll_id: uuid.UUID, option_index: int, session_id: str) -> bool:
        inserted = self._db.execute(
            pg_insert(PollVotes)
            .values(poll_id=poll_id, option_index=option_index, session_id=session_id)
            .on_conflict_do_nothing(index_elements=["poll_id", "session_id"])
            .returning(PollVotes.id)
        ).first()
        return inserted is not None

    # ── comments ─────────────────────────────────────────────────────────

    def approved_comments(self, post_id: uuid.UUID) -> list[PublicComment]:
        rows = self._db.scalars(
            select(Comments).where(Comments.blog_id == post_id, Comments.is_approved.is_(True)).order_by(Comments.created_at)
        ).all()
        return [
            PublicComment(r.id, r.parent_id, r.author_name or "Guest", r.user_id is not None, r.content, r.created_at)
            for r in rows
        ]

    def comment_post_id(self, comment_id: uuid.UUID) -> uuid.UUID | None:
        return self._db.scalar(select(Comments.blog_id).where(Comments.id == comment_id))

    def add_comment(
        self, *, post_id: uuid.UUID, parent_id: uuid.UUID | None, name: str, email: str | None, content: str
    ) -> None:
        self._db.add(Comments(blog_id=post_id, parent_id=parent_id, author_name=name, author_email=email, content=content))
        self._db.flush()

    # ── contact ──────────────────────────────────────────────────────────

    def add_contact_message(self, *, name: str, email: str, subject: str, message: str) -> None:
        self._db.add(ContactMessages(name=name, email=email, subject=subject, message=message))
        self._db.flush()

    # ── newsletter ───────────────────────────────────────────────────────

    @staticmethod
    def _subscriber(row: NewsletterSubscribers) -> Subscriber:
        return Subscriber(row.id, row.email, row.status.value, row.confirm_expires_at)

    def subscriber_by_email(self, email: str) -> Subscriber | None:
        row = self._db.scalar(select(NewsletterSubscribers).where(func.lower(NewsletterSubscribers.email) == email.lower()))
        return self._subscriber(row) if row else None

    def save_pending_subscriber(self, email: str, token: str, expires_at: datetime.datetime) -> None:
        row = self._db.scalar(select(NewsletterSubscribers).where(func.lower(NewsletterSubscribers.email) == email.lower()))
        if row is None:
            row = NewsletterSubscribers(email=email.lower(), status=SubscriberStatus.PENDING)
            self._db.add(row)
        row.status = SubscriberStatus.PENDING
        row.confirm_token = token
        row.confirm_expires_at = expires_at
        row.unsubscribed_at = None
        self._db.flush()

    def subscriber_by_confirm_token(self, token: str) -> Subscriber | None:
        row = self._db.scalar(select(NewsletterSubscribers).where(NewsletterSubscribers.confirm_token == token))
        return self._subscriber(row) if row else None

    def activate_subscriber(self, subscriber_id: uuid.UUID, now: datetime.datetime) -> None:
        self._db.execute(
            sa_update(NewsletterSubscribers).where(NewsletterSubscribers.id == subscriber_id).values(
                status=SubscriberStatus.ACTIVE, confirm_token=None, confirm_expires_at=None, confirmed_at=now,
            ).execution_options(synchronize_session=False)
        )

    def unsubscribe(self, token: str, now: datetime.datetime) -> bool:
        result = self._db.execute(
            sa_update(NewsletterSubscribers).where(NewsletterSubscribers.unsubscribe_token == token).values(
                status=SubscriberStatus.UNSUBSCRIBED, unsubscribed_at=now,
            ).execution_options(synchronize_session=False)
        )
        return result.rowcount > 0

    def unsubscribe_token_of(self, email: str) -> str | None:
        return self._db.scalar(
            select(NewsletterSubscribers.unsubscribe_token).where(func.lower(NewsletterSubscribers.email) == email.lower())
        )

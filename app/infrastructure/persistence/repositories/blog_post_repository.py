"""SQLAlchemy implementation of BlogPostRepository (infrastructure layer)."""
from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.entities.blog_post import (
    AuthorInfo,
    BlogMedia,
    BlogPost,
    BlogRevision,
    LinkTarget,
)
from app.domain.exceptions import BlogNotFoundError, VersionConflictError
from app.domain.repositories.blog_post_repository import BlogPostRepository
from app.infrastructure.persistence.orm.models import (
    BlogCategories,
    BlogPostRevisions,
    BlogPosts,
    BlogSlugRedirects,
    BlogStatus,
    Comments,
    ContentType,
    ContentVisibility,
    MediaAssets,
    Projects,
    Reactions,
    Users,
)

_ENUM_COLUMNS = {"status": BlogStatus, "visibility": ContentVisibility}


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlAlchemyBlogPostRepository(BlogPostRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    # ── working copy ──────────────────────────────────────────────────────

    def get(self, post_id: uuid.UUID, *, for_update: bool = False) -> BlogPost | None:
        stmt = select(BlogPosts).where(BlogPosts.id == post_id)
        if for_update:
            stmt = stmt.with_for_update()
        row = self._db.scalar(stmt)
        return self._to_entity(row) if row else None

    def add(self, fields: dict) -> BlogPost:
        row = BlogPosts(**self._columns(fields))
        self._db.add(row)
        # Flush (not commit): the request's get_db commits once it succeeds.
        self._db.flush()
        self._db.refresh(row)
        return self._to_entity(row)

    def update(self, post_id: uuid.UUID, expected_version: int | None, fields: dict) -> BlogPost:
        row = self._db.scalar(select(BlogPosts).where(BlogPosts.id == post_id).with_for_update())
        if row is None:
            raise BlogNotFoundError("POST_NOT_FOUND", f"Blog post {post_id} not found.")
        if expected_version is not None and row.version != expected_version:
            raise VersionConflictError(row.version, row.updated_at)
        for key, value in self._columns(fields).items():
            setattr(row, key, value)
        row.version = row.version + 1
        self._db.flush()
        self._db.refresh(row)  # pick up trigger-set updated_at / published_at
        return self._to_entity(row)

    def delete(self, post_id: uuid.UUID) -> None:
        # Reactions are polymorphic (no FK), so nothing cascades to them.
        # Comments are deleted explicitly too, so this works before and after
        # migration 006 adds ON DELETE CASCADE.
        self._db.execute(sa_delete(Reactions).where(
            Reactions.content_type == ContentType.BLOG_POST, Reactions.content_id == post_id
        ))
        self._db.execute(sa_delete(Comments).where(Comments.blog_id == post_id))
        self._db.execute(sa_delete(BlogPosts).where(BlogPosts.id == post_id))
        self._db.flush()

    def slug_owner(self, slug: str) -> uuid.UUID | None:
        return self._db.scalar(select(BlogPosts.id).where(BlogPosts.slug == slug))

    def redirect_owner(self, slug: str) -> uuid.UUID | None:
        return self._db.scalar(select(BlogSlugRedirects.post_id).where(BlogSlugRedirects.old_slug == slug))

    def add_redirect(self, old_slug: str, post_id: uuid.UUID) -> None:
        stmt = pg_insert(BlogSlugRedirects).values(old_slug=old_slug, post_id=post_id)
        stmt = stmt.on_conflict_do_update(index_elements=["old_slug"], set_={"post_id": post_id})
        self._db.execute(stmt)
        self._db.flush()

    def delete_redirect(self, slug: str) -> None:
        self._db.execute(sa_delete(BlogSlugRedirects).where(BlogSlugRedirects.old_slug == slug))
        self._db.flush()

    def due_scheduled_ids(self, limit: int) -> list[uuid.UUID]:
        stmt = (
            select(BlogPosts.id)
            .where(BlogPosts.status == BlogStatus.SCHEDULED, BlogPosts.scheduled_at <= func.now())
            .order_by(BlogPosts.scheduled_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self._db.scalars(stmt))

    # ── revisions ─────────────────────────────────────────────────────────

    def add_revision(self, *, post_id, kind, label, snapshot, content_html, content_hash,
                     word_count, created_by) -> BlogRevision:
        row = BlogPostRevisions(
            post_id=post_id, kind=kind, label=label, snapshot=snapshot,
            content_html=content_html, content_hash=content_hash,
            word_count=word_count, created_by=created_by,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return self._revision(row, self._user_name(created_by))

    def get_revision(self, post_id: uuid.UUID, revision_id: uuid.UUID) -> BlogRevision | None:
        stmt = self._revision_query().where(
            BlogPostRevisions.post_id == post_id, BlogPostRevisions.id == revision_id
        )
        hit = self._db.execute(stmt).first()
        return self._revision(*hit) if hit else None

    def latest_revision(self, post_id: uuid.UUID) -> BlogRevision | None:
        stmt = (
            self._revision_query()
            .where(BlogPostRevisions.post_id == post_id)
            .order_by(BlogPostRevisions.created_at.desc())
            .limit(1)
        )
        hit = self._db.execute(stmt).first()
        return self._revision(*hit) if hit else None

    def list_revisions(self, post_id, *, kind, page, limit):
        where = [BlogPostRevisions.post_id == post_id]
        if kind:
            where.append(BlogPostRevisions.kind == kind)
        total = self._db.scalar(select(func.count()).select_from(BlogPostRevisions).where(*where)) or 0
        stmt = (
            self._revision_query()
            .where(*where)
            .order_by(BlogPostRevisions.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return [self._revision(r, name) for r, name in self._db.execute(stmt).all()], total

    def prune_revisions(self, post_id: uuid.UUID, keep: int, protect: uuid.UUID | None) -> None:
        stale = (
            select(BlogPostRevisions.id)
            .where(BlogPostRevisions.post_id == post_id, BlogPostRevisions.kind.in_(("manual", "restore")))
            .order_by(BlogPostRevisions.created_at.desc())
            .offset(keep)
        )
        ids = [i for i in self._db.scalars(stale) if i != protect]
        if ids:
            self._db.execute(sa_delete(BlogPostRevisions).where(BlogPostRevisions.id.in_(ids)))
            self._db.flush()

    # ── lookups ───────────────────────────────────────────────────────────

    def get_media(self, asset_ids: list[uuid.UUID]) -> dict[uuid.UUID, BlogMedia]:
        if not asset_ids:
            return {}
        rows = self._db.scalars(select(MediaAssets).where(MediaAssets.id.in_(asset_ids)))
        return {row.id: self._media(row) for row in rows}

    def get_author(self, user_id: uuid.UUID) -> AuthorInfo | None:
        row = self._db.get(Users, user_id)
        return AuthorInfo(id=row.id, name=row.name, avatar_url=row.avatar_url) if row else None

    def category_exists(self, category_id: uuid.UUID) -> bool:
        return self._db.get(BlogCategories, category_id) is not None

    def list_tags(self, prefix: str, limit: int) -> list[tuple[str, int]]:
        rows = self._db.execute(
            text(
                "SELECT tag, count(*) AS n FROM blog_posts, unnest(tags) AS tag "
                "WHERE status <> 'archived' AND tag LIKE :prefix ESCAPE '\\' "
                "GROUP BY tag ORDER BY n DESC, tag LIMIT :limit"
            ),
            {"prefix": f"{_like_escape(prefix)}%", "limit": limit},
        )
        return [(tag, int(n)) for tag, n in rows]

    def search_link_targets(self, query: str, limit: int) -> list[LinkTarget]:
        pattern = f"%{_like_escape(query)}%"
        blogs = self._db.execute(
            select(BlogPosts.id, BlogPosts.title, BlogPosts.status, BlogPosts.slug)
            .where(BlogPosts.status != BlogStatus.ARCHIVED, BlogPosts.title.ilike(pattern, escape="\\"))
            .order_by(BlogPosts.updated_at.desc())
            .limit(limit)
        ).all()
        projects = self._db.execute(
            select(Projects.id, Projects.title, Projects.status, Projects.slug)
            .where(Projects.title.ilike(pattern, escape="\\"))
            .order_by(Projects.updated_at.desc())
            .limit(limit)
        ).all()
        targets = [
            LinkTarget("blog", str(i), title or slug, status.value, f"/blog/{slug}")
            for i, title, status, slug in blogs
        ] + [
            LinkTarget("project", str(i), title, status.value, f"/projects/{slug}")
            for i, title, status, slug in projects
        ]
        return targets[:limit]

    def link_target_status(self, kind: str, target_id: uuid.UUID) -> tuple[str, str] | None:
        if kind == "blog":
            hit = self._db.execute(
                select(BlogPosts.status, BlogPosts.slug).where(BlogPosts.id == target_id)
            ).first()
            return (hit[0].value, f"/blog/{hit[1]}") if hit else None
        hit = self._db.execute(select(Projects.status, Projects.slug).where(Projects.id == target_id)).first()
        return (hit[0].value, f"/projects/{hit[1]}") if hit else None

    # ── mapping ───────────────────────────────────────────────────────────

    @staticmethod
    def _columns(fields: dict) -> dict:
        out = {}
        for key, value in fields.items():
            enum_cls = _ENUM_COLUMNS.get(key)
            out[key] = enum_cls(value) if enum_cls and value is not None else value
        return out

    def _user_name(self, user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        return self._db.scalar(select(Users.name).where(Users.id == user_id))

    @staticmethod
    def _revision_query():
        return select(BlogPostRevisions, Users.name).outerjoin(Users, Users.id == BlogPostRevisions.created_by)

    @staticmethod
    def _revision(row: BlogPostRevisions, created_by_name: str | None) -> BlogRevision:
        return BlogRevision(
            id=row.id, post_id=row.post_id, kind=row.kind, label=row.label,
            snapshot=row.snapshot, content_html=row.content_html, content_hash=row.content_hash,
            word_count=row.word_count, created_by=row.created_by,
            created_by_name=created_by_name, created_at=row.created_at,
        )

    @staticmethod
    def _media(row: MediaAssets) -> BlogMedia:
        url = row.cloudinary_url
        if row.source_type == "youtube" and row.external_id:
            url = f"https://www.youtube.com/watch?v={row.external_id}"
        return BlogMedia(
            id=row.id,
            url=url,
            public_id=row.public_id,
            resource_type=row.resource_type.value if hasattr(row.resource_type, "value") else str(row.resource_type),
            source_type=row.source_type,
            width=row.width,
            height=row.height,
            alt_text=row.alt_text,
            thumbnail_url=row.thumbnail_url,
            external_id=row.external_id,
            video_title=row.video_title,
            video_duration_seconds=row.video_duration_seconds,
        )

    @staticmethod
    def _to_entity(row: BlogPosts) -> BlogPost:
        return BlogPost(
            id=row.id,
            title=row.title,
            subtitle=row.subtitle,
            slug=row.slug,
            slug_locked=row.slug_locked,
            content=row.content or {},
            content_html=row.content_html,
            content_text=row.content_text,
            content_hash=row.content_hash,
            excerpt=row.excerpt,
            category_id=row.category_id,
            tags=list(row.tags or []),
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            visibility=row.visibility.value if hasattr(row.visibility, "value") else str(row.visibility),
            allow_comments=row.allow_comments,
            seo=dict(row.seo or {}),
            author_id=row.author_id,
            cover_asset_id=row.cover_asset_id,
            og_asset_id=row.og_asset_id,
            cover_image_url=row.cover_image_url,
            og_image_url=row.og_image_url,
            word_count=row.word_count,
            block_count=row.block_count,
            read_time=row.read_time,
            version=row.version,
            published_revision_id=row.published_revision_id,
            scheduled_at=row.scheduled_at,
            published_at=row.published_at,
            last_published_at=row.last_published_at,
            schedule_error=row.schedule_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
            archived_at=row.archived_at,
        )


"""SQLAlchemy implementation of BlogListRepository (infrastructure layer).

Search is keyword + fuzzy, all in Postgres (Blog Manager API.md §5): the
weighted ``search_vector`` (migration 006) with a prefix query on the last
word, plus title substring, slug, tag and pg_trgm title similarity. User text
is only ever bound as a parameter; the prefix tsquery is built from
``SearchTerms.words``, which are ``[a-z0-9]+`` tokens and can't break
``to_tsquery`` syntax.
"""
from __future__ import annotations

import datetime
import html
import uuid

from sqlalchemy import Text, and_, case, cast, false, func, literal, literal_column, or_, select, true
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, array
from sqlalchemy.orm import Session, aliased

from app.domain.blog.slug import slugify
from app.domain.entities.blog_post import BlogStatusStats, PostListQuery, PostListRow, SearchTerms
from app.domain.repositories.blog_list_repository import BlogListRepository
from app.infrastructure.persistence.orm.models import (
    BlogCategories,
    BlogPostRevisions,
    BlogPosts,
    BlogStatus,
    MediaAssets,
    Users,
)
from app.infrastructure.persistence.repositories.blog_post_repository import _like_escape

_SEARCH_VECTOR = literal_column("blog_posts.search_vector", type_=TSVECTOR)
_TITLE_SIMILARITY = 0.4
# ts_headline markers that can't occur in normal text; swapped for <mark>
# after the snippet is HTML-escaped.
_MARK_OPEN, _MARK_CLOSE = "⁣[[", "]]⁣"


class _Search:
    """The SQL expressions for one search, built once per request."""

    def __init__(self, terms: SearchTerms) -> None:
        words = terms.words
        tag_words = sorted({*words, slugify(terms.text)} - {""})
        self.prefix_query = func.to_tsquery("english", " & ".join([*words[:-1], f"{words[-1]}:*"]))
        web_query = func.websearch_to_tsquery("english", terms.text)
        self.title_hit = BlogPosts.title.ilike(f"%{_like_escape(terms.text)}%", escape="\\")
        self.slug_hit = BlogPosts.slug.ilike(f"%{_like_escape('-'.join(words))}%", escape="\\")
        self.tag_hit = BlogPosts.tags.op("&&", is_comparison=True)(cast(array(tag_words), ARRAY(Text)))
        self.similarity = func.word_similarity(terms.text, BlogPosts.title)
        self.text_hit = or_(_SEARCH_VECTOR.op("@@", is_comparison=True)(self.prefix_query),
                            _SEARCH_VECTOR.op("@@", is_comparison=True)(web_query))
        self.title_words_hit = func.to_tsvector("english", BlogPosts.title).op("@@", is_comparison=True)(self.prefix_query)
        self.condition = or_(
            self.text_hit, self.title_hit, self.slug_hit, self.tag_hit, self.similarity > _TITLE_SIMILARITY
        )
        self.rank = (
            case((self.title_hit, 2.0), else_=0.0)
            + func.ts_rank_cd(_SEARCH_VECTOR, self.prefix_query)
            + case((self.tag_hit, 0.6), else_=0.0)
            + case((self.slug_hit, 0.4), else_=0.0)
            + 0.8 * self.similarity
        )
        self.snippet = func.ts_headline(
            "english",
            func.coalesce(BlogPosts.excerpt, "") + " " + func.left(BlogPosts.content_text, 3000),
            self.prefix_query,
            f"StartSel={_MARK_OPEN}, StopSel={_MARK_CLOSE}, MaxWords=20, MinWords=8, MaxFragments=1",
        )


def _status_condition(statuses: tuple[str, ...] | None):
    if statuses is None:
        return BlogPosts.status != BlogStatus.ARCHIVED
    wanted = set(statuses)
    if "draft" in wanted:
        wanted.add("review")  # legacy status, shown as draft
    return BlogPosts.status.in_([BlogStatus(s) for s in wanted])


def _category_condition(category: uuid.UUID | str | None):
    if category is None:
        return true()
    if category == "none":
        return BlogPosts.category_id.is_(None)
    return BlogPosts.category_id == category


def _snippet_html(raw: str | None) -> str | None:
    if not raw or _MARK_OPEN not in raw:
        return None
    escaped = html.escape(raw.strip(), quote=False)
    return escaped.replace(_MARK_OPEN, "<mark>").replace(_MARK_CLOSE, "</mark>")


class SqlAlchemyBlogListRepository(BlogListRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_posts(self, query: PostListQuery) -> tuple[list[PostListRow], int]:
        search = _Search(query.search) if query.search else None
        where = [
            BlogPosts.author_id == query.author_id,
            _status_condition(query.statuses),
            _category_condition(query.category),
            search.condition if search else true(),
        ]
        total = self._db.scalar(select(func.count()).select_from(BlogPosts).where(*where)) or 0

        live = aliased(BlogPostRevisions)
        changed = and_(
            BlogPosts.status == BlogStatus.PUBLISHED,
            BlogPosts.content_hash.is_distinct_from(live.content_hash),
        )
        search_cols = (
            [
                search.rank.label("rank"),
                or_(search.title_hit, search.title_words_hit, search.similarity > _TITLE_SIMILARITY).label("m_title"),
                search.tag_hit.label("m_tags"),
                search.slug_hit.label("m_slug"),
                search.text_hit.label("m_text"),
                search.snippet.label("snippet"),
            ]
            if search else
            [literal(None).label("rank"), false().label("m_title"), false().label("m_tags"),
             false().label("m_slug"), false().label("m_text"), literal(None, Text).label("snippet")]
        )
        stmt = (
            select(
                BlogPosts.id, BlogPosts.title, BlogPosts.slug, BlogPosts.excerpt,
                func.left(BlogPosts.content_text, 160).label("body_start"),
                BlogPosts.status, changed.label("changed"),
                BlogPosts.category_id, BlogCategories.name.label("category_name"),
                BlogCategories.slug.label("category_slug"),
                BlogPosts.tags, BlogPosts.cover_asset_id,
                MediaAssets.cloudinary_url.label("cover_url"), MediaAssets.alt_text.label("cover_alt"),
                BlogPosts.read_time, BlogPosts.word_count, BlogPosts.views,
                BlogPosts.author_id, Users.name.label("author_name"), BlogPosts.version,
                BlogPosts.scheduled_at, BlogPosts.schedule_error, BlogPosts.published_at,
                BlogPosts.archived_at, BlogPosts.created_at, BlogPosts.updated_at,
                *search_cols,
            )
            .outerjoin(BlogCategories, BlogCategories.id == BlogPosts.category_id)
            .outerjoin(MediaAssets, MediaAssets.id == BlogPosts.cover_asset_id)
            .outerjoin(Users, Users.id == BlogPosts.author_id)
            .outerjoin(live, live.id == BlogPosts.published_revision_id)
            .where(*where)
            .order_by(*self._order(query, search), BlogPosts.id)
            .offset((query.page - 1) * query.limit)
            .limit(query.limit)
        )
        return [self._row(r) for r in self._db.execute(stmt).all()], total

    def facet_counts(self, query: PostListQuery) -> tuple[dict[str, int], dict[str, int]]:
        search_cond = _Search(query.search).condition if query.search else true()
        mine = BlogPosts.author_id == query.author_id

        by_status: dict[str, int] = {}
        for status, n in self._db.execute(
            select(BlogPosts.status, func.count())
            .where(mine, _category_condition(query.category), search_cond)
            .group_by(BlogPosts.status)
        ).all():
            key = "draft" if status == BlogStatus.REVIEW else status.value
            by_status[key] = by_status.get(key, 0) + int(n)

        by_category: dict[str, int] = {}
        for category_id, n in self._db.execute(
            select(BlogPosts.category_id, func.count())
            .where(mine, _status_condition(query.statuses), search_cond)
            .group_by(BlogPosts.category_id)
        ).all():
            by_category[str(category_id) if category_id else "none"] = int(n)
        return by_status, by_category

    def status_stats(self, author_id: uuid.UUID, created_since: datetime.datetime) -> BlogStatusStats:
        mine = BlogPosts.author_id == author_id
        counts: dict[str, int] = {}
        for status, n in self._db.execute(
            select(BlogPosts.status, func.count()).where(mine).group_by(BlogPosts.status)
        ).all():
            key = "draft" if status == BlogStatus.REVIEW else status.value
            counts[key] = counts.get(key, 0) + int(n)

        created, next_at, failed = self._db.execute(
            select(
                func.count().filter(
                    BlogPosts.created_at >= created_since, BlogPosts.status != BlogStatus.ARCHIVED
                ),
                func.min(BlogPosts.scheduled_at).filter(BlogPosts.status == BlogStatus.SCHEDULED),
                func.count().filter(
                    BlogPosts.status == BlogStatus.DRAFT, BlogPosts.schedule_error.is_not(None)
                ),
            ).where(mine)
        ).one()
        return BlogStatusStats(
            counts=counts, created_since=int(created or 0), next_scheduled_at=next_at,
            failed_schedules=int(failed or 0),
        )

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _order(query: PostListQuery, search: _Search | None) -> list:
        desc = query.descending
        if query.sort == "relevance" and search is not None:
            return [search.rank.desc(), BlogPosts.updated_at.desc()]
        if query.sort == "title":
            key = func.lower(func.nullif(BlogPosts.title, ""))
            return [(key.desc() if desc else key.asc()).nulls_last()]
        column = {
            "published_at": BlogPosts.published_at,
            "created_at": BlogPosts.created_at,
            "views": BlogPosts.views,
        }.get(query.sort, BlogPosts.updated_at)
        return [(column.desc() if desc else column.asc()).nulls_last()]

    @staticmethod
    def _row(r) -> PostListRow:
        matched = tuple(
            name for name, hit in (("title", r.m_title), ("tags", r.m_tags), ("slug", r.m_slug), ("content", r.m_text))
            if hit
        )
        status = r.status.value if hasattr(r.status, "value") else str(r.status)
        return PostListRow(
            id=r.id, title=r.title, slug=r.slug, excerpt=r.excerpt, body_start=r.body_start or "",
            status="draft" if status == "review" else status,
            has_unpublished_changes=bool(r.changed),
            category_id=r.category_id, category_name=r.category_name, category_slug=r.category_slug,
            tags=list(r.tags or []), cover_asset_id=r.cover_asset_id,
            cover_url=r.cover_url, cover_alt=r.cover_alt,
            read_time=r.read_time, word_count=r.word_count, views=r.views,
            author_id=r.author_id, author_name=r.author_name, version=r.version,
            scheduled_at=r.scheduled_at, schedule_error=r.schedule_error,
            published_at=r.published_at, archived_at=r.archived_at,
            created_at=r.created_at, updated_at=r.updated_at,
            rank=float(r.rank) if r.rank is not None else None,
            matched=matched, snippet=_snippet_html(r.snippet),
        )

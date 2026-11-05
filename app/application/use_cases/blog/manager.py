"""Blog Manager use cases (application layer).

ListBlogPosts, GetBlogStats, BulkBlogAction (archive / delete) and
UnarchiveBlogPost. Contract: "Blog Manager API.md" (endpoints 24–27).
Reads go through BlogListRepository; every write goes through the editor's
BlogPostWorkflow so locking, versioning and activity logging stay identical.
"""
from __future__ import annotations

import datetime
import math
import re
import uuid
from zoneinfo import ZoneInfo

from app.application.dtos.blog import (
    BULK_ACTIONS,
    BULK_MAX_ITEMS,
    LIST_MAX_LIMIT,
    LIST_SORTS,
    LIST_STATUSES,
    SEARCH_MAX_CHARS,
    SEARCH_MIN_CHARS,
    BlogSettings,
    BlogStatsView,
    BulkFailure,
    BulkResultView,
    PostListItemView,
    PostListParams,
    PostListResult,
    PostView,
)
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow, cloudinary_variant, utcnow
from app.domain.entities.blog_post import PostListQuery, PostListRow, SearchTerms
from app.domain.exceptions import (
    BlogNotFoundError,
    BlogRuleError,
    InvalidStateError,
    PermissionError,
    VersionConflictError,
)
from app.domain.repositories.blog_list_repository import BlogListRepository

_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_COVER_THUMB = "c_fill,g_auto,w_128,h_88,f_auto,q_auto"
_EXCERPT_FALLBACK_CHARS = 160


def _invalid(field: str, message: str) -> BlogRuleError:
    return BlogRuleError("VALIDATION_ERROR", message, {"fields": {field: message}})


# ── list ─────────────────────────────────────────────────────────────────────


class ListBlogPosts:
    def __init__(self, repo: BlogListRepository) -> None:
        self._repo = repo

    def execute(self, author_id: uuid.UUID, params: PostListParams) -> PostListResult:
        statuses = self._statuses(params.statuses)
        category = self._category(params.category_id)
        search = self._search(params.q)
        sort = self._sort(params.sort, search is not None)
        descending = self._descending(params.dir, sort)
        limit = min(max(1, params.limit), LIST_MAX_LIMIT)
        page = max(1, params.page)

        query = PostListQuery(
            author_id=author_id, statuses=statuses, category=category, search=search,
            sort=sort, descending=descending, page=page, limit=limit,
        )
        rows, total = self._repo.list_posts(query)
        by_status, by_category = self._repo.facet_counts(query)

        return PostListResult(
            items=[self._item(r, search is not None) for r in rows],
            total=total,
            page=page,
            limit=limit,
            total_pages=max(1, math.ceil(total / limit)),
            facets={
                "status": {
                    "all": sum(n for s, n in by_status.items() if s != "archived"),
                    **{s: by_status.get(s, 0) for s in LIST_STATUSES},
                },
                "category": {"all": sum(by_category.values()), "none": by_category.get("none", 0), **by_category},
            },
            applied={
                "status": list(statuses or []),
                "category_id": str(category) if category else None,
                "q": search.text if search else None,
                "sort": sort,
                "dir": "desc" if descending else "asc",
            },
        )

    # ── parameter rules (API §4.1) ──

    @staticmethod
    def _statuses(raw: list[str]) -> tuple[str, ...] | None:
        seen: list[str] = []
        for chunk in raw:
            for value in chunk.split(","):
                value = value.strip().lower()
                if not value:
                    continue
                if value not in LIST_STATUSES:
                    raise _invalid("status", f"status must be one of: {', '.join(LIST_STATUSES)}.")
                if value not in seen:
                    seen.append(value)
        return tuple(seen) or None

    @staticmethod
    def _category(raw: str | None) -> uuid.UUID | str | None:
        if raw is None or not raw.strip():
            return None
        raw = raw.strip()
        if raw.lower() == "none":
            return "none"
        try:
            return uuid.UUID(raw)
        except ValueError as exc:
            raise _invalid("category_id", "category_id must be a UUID or 'none'.") from exc

    @staticmethod
    def _search(raw: str | None) -> SearchTerms | None:
        text = (raw or "").strip()
        if len(text) > SEARCH_MAX_CHARS:
            raise _invalid("q", f"Search is limited to {SEARCH_MAX_CHARS} characters.")
        words = tuple(_WORDS.findall(text.lower()))
        if len(text) < SEARCH_MIN_CHARS or not words:
            return None  # too short or punctuation only → full list
        return SearchTerms(text=text, words=words)

    @staticmethod
    def _sort(raw: str | None, searching: bool) -> str:
        if not raw:
            return "relevance" if searching else "updated_at"
        if raw not in LIST_SORTS:
            raise _invalid("sort", f"sort must be one of: {', '.join(LIST_SORTS)}.")
        return raw if raw != "relevance" or searching else "updated_at"

    @staticmethod
    def _descending(raw: str | None, sort: str) -> bool:
        if not raw:
            return sort != "title"
        if raw.lower() not in ("asc", "desc"):
            raise _invalid("dir", "dir must be 'asc' or 'desc'.")
        return raw.lower() == "desc"

    @staticmethod
    def _item(r: PostListRow, searching: bool) -> PostListItemView:
        excerpt = r.excerpt or (r.body_start.strip()[:_EXCERPT_FALLBACK_CHARS] or None)
        return PostListItemView(
            id=r.id,
            title=r.title,
            slug=r.slug,
            excerpt=excerpt,
            status=r.status,
            has_unpublished_changes=r.has_unpublished_changes,
            category=(
                {"id": r.category_id, "name": r.category_name, "slug": r.category_slug}
                if r.category_id and r.category_name else None
            ),
            tags=r.tags,
            cover=(
                {"id": r.cover_asset_id, "thumb_url": cloudinary_variant(r.cover_url, _COVER_THUMB),
                 "alt": r.cover_alt or ""}
                if r.cover_asset_id and r.cover_url else None
            ),
            read_time=r.read_time,
            word_count=r.word_count,
            views=r.views,
            author={"id": r.author_id, "name": r.author_name} if r.author_name else None,
            version=r.version,
            scheduled_at=r.scheduled_at,
            schedule_error=r.schedule_error,
            published_at=r.published_at,
            archived_at=r.archived_at,
            created_at=r.created_at,
            updated_at=r.updated_at,
            search=(
                {"rank": round(r.rank or 0.0, 4), "matched": list(r.matched), "snippet": r.snippet}
                if searching else None
            ),
        )


# ── stats ────────────────────────────────────────────────────────────────────


class GetBlogStats:
    def __init__(self, repo: BlogListRepository, settings: BlogSettings, clock=utcnow) -> None:
        self._repo = repo
        self._settings = settings
        self._clock = clock

    def execute(self, author_id: uuid.UUID) -> BlogStatsView:
        local_now = self._clock().astimezone(ZoneInfo(self._settings.timezone))
        month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stats = self._repo.status_stats(author_id, month_start)
        c = stats.counts
        published, draft, scheduled = c.get("published", 0), c.get("draft", 0), c.get("scheduled", 0)
        return BlogStatsView(
            total=published + draft + scheduled,
            published=published,
            draft=draft,
            scheduled=scheduled,
            archived=c.get("archived", 0),
            created_this_month=stats.created_since,
            next_scheduled_at=stats.next_scheduled_at,
            failed_schedules=stats.failed_schedules,
        )


# ── bulk archive / delete ────────────────────────────────────────────────────


class BulkBlogAction:
    """Archive or delete many posts; each post succeeds or fails on its own.

    Every rule is checked before anything is written for that post, so a
    refused post leaves no partial change. Rows are locked in id order so two
    overlapping bulk requests can't deadlock.
    """

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, actor_id: uuid.UUID, action: str, items: list[tuple[uuid.UUID, int]]) -> BulkResultView:
        if action not in BULK_ACTIONS:
            raise _invalid("action", f"action must be one of: {', '.join(BULK_ACTIONS)}.")
        versions = dict(items)  # duplicates merged, last version wins
        if not versions:
            raise _invalid("items", "Select at least one post.")
        if len(versions) > BULK_MAX_ITEMS:
            raise _invalid("items", f"At most {BULK_MAX_ITEMS} posts per request.")

        succeeded: list[uuid.UUID] = []
        failed: list[BulkFailure] = []
        for post_id in sorted(versions, key=str):
            try:
                self._apply(action, post_id, versions[post_id], actor_id)
                succeeded.append(post_id)
            except VersionConflictError as exc:
                failed.append(BulkFailure(post_id, "VERSION_CONFLICT",
                                          "This post changed since the list loaded.", exc.current_version))
            except BlogNotFoundError as exc:
                failed.append(BulkFailure(post_id, exc.code, "This post no longer exists."))
            except PermissionError as exc:
                failed.append(BulkFailure(post_id, "FORBIDDEN", str(exc)))
            except InvalidStateError as exc:
                failed.append(BulkFailure(post_id, exc.code, str(exc)))
        return BulkResultView(action=action, requested=len(versions), succeeded=succeeded, failed=failed)

    def _apply(self, action: str, post_id: uuid.UUID, version: int, actor_id: uuid.UUID) -> None:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        wf.check_version(post, version)
        if action == "archive":
            wf.archive(post, actor_id)
            return

        if post.status == "scheduled":
            raise InvalidStateError("POST_SCHEDULED", "Open it and unschedule, or archive it.")
        if post.status != "archived" and (post.status == "published" or post.published_at is not None):
            raise InvalidStateError("POST_WAS_PUBLISHED", "This post has been live. Archive it first.")
        wf.record("blog_deleted", post, actor_id, f"Blog post '{post.title or post.slug}' deleted.",
                  {"previous_status": post.status})
        wf.repo.delete(post.id)


# ── restore ──────────────────────────────────────────────────────────────────


class UnarchiveBlogPost:
    """archived → draft. Never straight back to live: the post must pass the
    checklist again when it is republished."""

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> PostView:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        if post.status != "archived":
            raise InvalidStateError("NOT_ARCHIVED", "This post is not archived.")
        wf.check_version(post, version)
        updated = wf.repo.update(post.id, version, {"status": "draft", "archived_at": None})
        wf.record("blog_updated", updated, actor_id,
                  f"Blog post '{updated.title or updated.slug}' restored from the archive.",
                  {"action": "unarchived"})
        return wf.view(updated)

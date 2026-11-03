"""Shared blog post workflow (application layer).

Not a use case itself — the rules every blog use case shares, kept in one
place so create, update, restore, publish and the scheduler can't drift apart:

  * ``apply_changes``  validate editor fields → column values (content is
                       normalized and rendered, slug derived, hash computed)
  * ``checklist``      evaluate the before-publish rules for a post
  * ``view``           build the editor's PostView
  * ``publish``        the one publish routine (button and scheduler)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import re
import uuid
from collections.abc import Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.application.dtos.blog import (
    BlogSettings,
    PostStats,
    PostView,
    SaveWarning,
    SeoEffective,
)
from app.application.interfaces.blog_content_renderer import BlogContentRenderer
from app.domain.blog import checklist as checklist_rules
from app.domain.blog.content_schema import normalize_document
from app.domain.blog.slug import fallback_slug, slug_issue, slugify, suggest_free
from app.domain.entities.blog_post import BlogMedia, BlogPost
from app.domain.exceptions import (
    BlogNotFoundError,
    BlogRuleError,
    ChecklistFailedError,
    InvalidStateError,
    PermissionError,
    SlugTakenError,
    VersionConflictError,
)
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.blog_category_repository import BlogCategoryRepository
from app.domain.repositories.blog_post_repository import BlogPostRepository

TITLE_MAX = 150
SUBTITLE_MAX = 200
EXCERPT_HARD_MAX = 300
TAGS_MAX = 8
TAG_LEN = (2, 30)
META_TITLE_MAX = 70
META_DESCRIPTION_MAX = 200

# The fields whose change means "the live page is out of date".
PUBLISHABLE_FIELDS = (
    "title", "subtitle", "slug", "content", "excerpt", "cover_asset_id", "og_asset_id",
    "category_id", "tags", "seo", "allow_comments",
)
# Extra columns a revision snapshot carries so it can be restored verbatim.
SNAPSHOT_EXTRA = ("slug_locked", "cover_image_url", "og_image_url")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _vfail(field: str, message: str) -> BlogRuleError:
    return BlogRuleError("VALIDATION_ERROR", message, {"fields": {field: message}})


def normalize_tag(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")


def _json_default(value):
    if isinstance(value, (uuid.UUID, datetime.datetime)):
        return str(value)
    raise TypeError(type(value))


class BlogPostWorkflow:
    def __init__(
        self,
        *,
        repo: BlogPostRepository,
        categories: BlogCategoryRepository,
        renderer: BlogContentRenderer,
        activity: ActivityLogRepository,
        settings: BlogSettings,
        clock: Callable[[], datetime.datetime] = utcnow,
    ) -> None:
        self.repo = repo
        self.categories = categories
        self.renderer = renderer
        self.activity = activity
        self.settings = settings
        self.clock = clock

    # ── loading ───────────────────────────────────────────────────────────

    def load(self, post_id: uuid.UUID, actor_id: uuid.UUID | None, *, for_update: bool = False) -> BlogPost:
        post = self.repo.get(post_id, for_update=for_update)
        if post is None:
            raise BlogNotFoundError("POST_NOT_FOUND", f"Blog post {post_id} not found.")
        if actor_id is not None and post.author_id != actor_id:
            raise PermissionError("You do not have access to this post.")
        return post

    @staticmethod
    def check_version(post: BlogPost, version: int) -> None:
        if post.version != version:
            raise VersionConflictError(post.version, post.updated_at)

    @staticmethod
    def ensure_editable(post: BlogPost) -> None:
        if post.status == "archived":
            raise InvalidStateError("POST_ARCHIVED", "Archived posts are read-only.")

    # ── field validation ──────────────────────────────────────────────────

    def apply_changes(
        self, changes: dict, existing: BlogPost | None
    ) -> tuple[dict, list[SaveWarning], bool]:
        """Turn editor field changes into column values.

        Returns (columns, warnings, slug_adjusted). ``columns`` always carries
        the recomputed ``content_hash`` so callers can write it in one go.
        """
        cols: dict = {}
        warnings: list[SaveWarning] = []

        if "title" in changes:
            title = (changes["title"] or "").replace("\n", " ").strip()
            if len(title) > TITLE_MAX:
                raise _vfail("title", f"Title can be at most {TITLE_MAX} characters.")
            cols["title"] = title
        if "subtitle" in changes:
            cols["subtitle"] = self._text(changes["subtitle"], "subtitle", SUBTITLE_MAX)
        if "excerpt" in changes:
            cols["excerpt"] = self._text(changes["excerpt"], "excerpt", EXCERPT_HARD_MAX)
        if "allow_comments" in changes and changes["allow_comments"] is not None:
            cols["allow_comments"] = bool(changes["allow_comments"])
        if "tags" in changes:
            cols["tags"] = self._tags(changes["tags"] or [])
        if "seo" in changes:
            cols["seo"] = self._seo(changes["seo"] or {}, existing.seo if existing else {})
        if "category_id" in changes:
            cid = changes["category_id"]
            if cid is not None and not self.repo.category_exists(cid):
                raise BlogRuleError("CATEGORY_NOT_FOUND", "That category no longer exists.")
            cols["category_id"] = cid
        for key, url_col in (("cover_asset_id", "cover_image_url"), ("og_asset_id", "og_image_url")):
            if key in changes:
                cols[key], cols[url_col] = self._image_asset(changes[key], key)

        if "content" in changes:
            content, facts = normalize_document(changes["content"])
            rendered = self.renderer.render(content)
            cols.update(
                content=content,
                content_html=rendered.html,
                content_text=rendered.text,
                word_count=rendered.word_count,
                block_count=rendered.block_count,
                read_time=self.reading_time(rendered.word_count),
                content_schema_version=content["schema_version"],
            )
            warnings.extend(self._link_warnings(facts.internal_links))

        slug_adjusted = self._apply_slug(changes, existing, cols)

        merged = self.publishable_state(existing, cols)
        cols["content_hash"] = self.hash_state(merged)
        return cols, warnings, slug_adjusted

    @staticmethod
    def _text(value, field: str, limit: int) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if len(value) > limit:
            raise _vfail(field, f"{field.capitalize()} can be at most {limit} characters.")
        return value or None

    @staticmethod
    def _tags(raw_tags: list) -> list[str]:
        tags: list[str] = []
        for raw in raw_tags:
            tag = normalize_tag(str(raw))
            if not tag or tag in tags:
                continue
            if not TAG_LEN[0] <= len(tag) <= TAG_LEN[1]:
                raise _vfail("tags", f"Tags must be {TAG_LEN[0]}–{TAG_LEN[1]} characters ('{tag}').")
            tags.append(tag)
        if len(tags) > TAGS_MAX:
            raise _vfail("tags", f"At most {TAGS_MAX} tags.")
        return tags

    @staticmethod
    def _seo(raw: dict, current: dict) -> dict:
        seo = {k: current.get(k) for k in ("meta_title", "meta_description", "canonical_url")}
        for key, limit in (("meta_title", META_TITLE_MAX), ("meta_description", META_DESCRIPTION_MAX)):
            if key in raw:
                value = (raw[key] or "").strip() or None
                if value and len(value) > limit:
                    raise _vfail(f"seo.{key}", f"Must be at most {limit} characters.")
                seo[key] = value
        if "canonical_url" in raw:
            value = (raw["canonical_url"] or "").strip() or None
            if value:
                parsed = urlparse(value)
                if parsed.scheme != "https" or not parsed.netloc:
                    raise _vfail("seo.canonical_url", "Canonical URL must be an absolute https:// URL.")
            seo["canonical_url"] = value
        return seo

    def _image_asset(self, asset_id, field: str) -> tuple[uuid.UUID | None, str | None]:
        if asset_id is None:
            return None, None
        media = self.repo.get_media([asset_id]).get(asset_id)
        if media is None:
            raise BlogRuleError("MEDIA_NOT_FOUND", "That image is no longer in the media library.",
                                {"field": field})
        if media.resource_type != "image" or media.source_type != "cloudinary":
            raise BlogRuleError("MEDIA_TYPE_MISMATCH", "Pick an image, not a video.", {"field": field})
        return asset_id, media.url

    def _link_warnings(self, internal_links: list[dict]) -> list[SaveWarning]:
        warnings = []
        for ref in internal_links:
            target = self.repo.link_target_status(ref["type"], uuid.UUID(ref["id"]))
            if target is None:
                warnings.append(SaveWarning("LINK_TARGET_MISSING", "A link points to deleted content."))
            elif target[0] != "published":
                warnings.append(SaveWarning("LINK_TO_DRAFT", "A link points to unpublished content."))
        return warnings

    # ── slug ──────────────────────────────────────────────────────────────

    def _taken_by_other(self, slug: str, post_id: uuid.UUID | None) -> bool:
        owner = self.repo.slug_owner(slug)
        if owner is not None and owner != post_id:
            return True
        redirect = self.repo.redirect_owner(slug)
        return redirect is not None and redirect != post_id

    def _apply_slug(self, changes: dict, existing: BlogPost | None, cols: dict) -> bool:
        post_id = existing.id if existing else None
        locked = existing.slug_locked if existing else False
        if "slug_locked" in changes and changes["slug_locked"] is not None:
            locked = bool(changes["slug_locked"])

        if changes.get("slug"):
            # A hand-edited slug locks it.
            slug = slugify(changes["slug"])
            problem = slug_issue(slug)
            if problem == "reserved":
                raise BlogRuleError("RESERVED_SLUG", f"'{slug}' is reserved.", {"slug": slug})
            if problem:
                raise _vfail("slug", f"Slug is {problem.replace('_', ' ')}.")
            if self._taken_by_other(slug, post_id):
                raise SlugTakenError(slug, suggest_free(slug, lambda s: self._taken_by_other(s, post_id)))
            cols.update(slug=slug, slug_locked=True)
            return False

        cols["slug_locked"] = locked
        ever_published = existing is not None and existing.published_at is not None
        title_changed = "title" in cols and (existing is None or cols["title"] != existing.title)
        unlocked_now = existing is not None and existing.slug_locked and not locked
        if locked or ever_published or not (existing is None or title_changed or unlocked_now):
            return False

        title = cols.get("title", existing.title if existing else "")
        base = slugify(title)
        if slug_issue(base) in ("too_short", "invalid", "reserved"):
            if existing is not None:
                return False
            base = fallback_slug()
        free = suggest_free(base, lambda s: self._taken_by_other(s, post_id))
        cols["slug"] = free
        return free != base

    # ── hashing & snapshots ──────────────────────────────────────────────

    @staticmethod
    def publishable_state(existing: BlogPost | None, cols: dict) -> dict:
        state = {}
        for key in PUBLISHABLE_FIELDS:
            if key in cols:
                state[key] = cols[key]
            elif existing is not None:
                state[key] = getattr(existing, key)
            else:
                state[key] = None
        # Normalize empties so "unset" and "default" hash the same — otherwise a
        # no-op save would flag the live post as having unpublished changes.
        seo = state["seo"] or {}
        state["seo"] = {k: seo.get(k) for k in ("meta_title", "meta_description", "canonical_url")}
        state["tags"] = list(state["tags"] or [])
        state["content"] = state["content"] or {}
        state["allow_comments"] = True if state["allow_comments"] is None else state["allow_comments"]
        state["title"] = state["title"] or ""
        for key in ("cover_asset_id", "og_asset_id", "category_id"):
            state[key] = str(state[key]) if state[key] else None
        return state

    @staticmethod
    def hash_state(state: dict) -> str:
        payload = json.dumps(state, sort_keys=True, default=_json_default, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def snapshot(post: BlogPost) -> dict:
        data = {key: getattr(post, key) for key in PUBLISHABLE_FIELDS + SNAPSHOT_EXTRA}
        return json.loads(json.dumps(data, default=_json_default))

    def columns_from_snapshot(self, snapshot: dict) -> dict:
        """Snapshot → column values (re-rendered, so HTML follows renderer fixes)."""
        cols = {key: snapshot.get(key) for key in PUBLISHABLE_FIELDS + SNAPSHOT_EXTRA}
        for key in ("cover_asset_id", "og_asset_id", "category_id"):
            cols[key] = uuid.UUID(cols[key]) if cols[key] else None
        cols["tags"] = cols["tags"] or []
        cols["seo"] = cols["seo"] or {}
        content, _ = normalize_document(cols["content"])
        rendered = self.renderer.render(content)
        cols.update(
            content=content,
            content_html=rendered.html,
            content_text=rendered.text,
            word_count=rendered.word_count,
            block_count=rendered.block_count,
            read_time=self.reading_time(rendered.word_count),
        )
        cols["content_hash"] = self.hash_state(self.publishable_state(None, cols))
        return cols

    def reading_time(self, words: int) -> int:
        return max(1, math.ceil(words / self.settings.words_per_minute)) if words else 0

    # ── derived views ────────────────────────────────────────────────────

    def live_hash(self, post: BlogPost) -> str | None:
        if post.published_revision_id is None:
            return None
        rev = self.repo.get_revision(post.id, post.published_revision_id)
        return rev.content_hash if rev else None

    def has_unpublished_changes(self, post: BlogPost) -> bool:
        return post.status == "published" and self.live_hash(post) != post.content_hash

    def seo_effective(self, post: BlogPost) -> SeoEffective:
        seo = post.seo or {}
        og_url = post.og_image_url or post.cover_image_url
        return SeoEffective(
            meta_title=seo.get("meta_title") or f"{post.title}{self.settings.title_suffix}",
            meta_description=seo.get("meta_description") or post.excerpt or "",
            canonical_url=seo.get("canonical_url") or self.settings.public_url(post.slug),
            og_image_url=_cloudinary_variant(og_url, "c_fill,g_auto,w_1200,h_630,f_auto,q_auto") if og_url else None,
        )

    def checklist(self, post: BlogPost) -> checklist_rules.Checklist:
        _, facts = normalize_document(post.content or None)
        wanted = {uuid.UUID(a) for a in facts.asset_ids}
        for asset_id in (post.cover_asset_id, post.og_asset_id):
            if asset_id:
                wanted.add(asset_id)
        found = self.repo.get_media(list(wanted)) if wanted else {}
        missing = []
        if post.cover_asset_id and post.cover_asset_id not in found:
            missing.append("cover image")
        if post.og_asset_id and post.og_asset_id not in found:
            missing.append("social image")
        body_missing = sum(1 for a in facts.asset_ids if uuid.UUID(a) not in found)
        if body_missing:
            missing.append(f"{body_missing} image(s)/video(s) in the body")

        slug_problem = slug_issue(post.slug)
        if slug_problem is None and self._taken_by_other(post.slug, post.id):
            slug_problem = "taken"
        seo = self.seo_effective(post)
        return checklist_rules.evaluate(checklist_rules.ChecklistInput(
            title=post.title,
            slug_problem=slug_problem,
            category_ok=post.category_id is not None and self.repo.category_exists(post.category_id),
            excerpt=post.excerpt,
            word_count=post.word_count,
            images_missing_alt=facts.images_missing_alt,
            missing_media=missing,
            empty_blocks=facts.empty_blocks,
            heading_order_ok=facts.heading_order_ok,
            has_cover=post.cover_asset_id is not None,
            has_og=post.og_asset_id is not None,
            tag_count=len(post.tags),
            meta_title=seo.meta_title,
            meta_description=seo.meta_description,
        ))

    def stats(self, post: BlogPost) -> PostStats:
        _, facts = normalize_document(post.content or None)
        images = sum(1 for _ in facts.asset_ids)
        return PostStats(
            word_count=post.word_count,
            reading_time_min=post.read_time or self.reading_time(post.word_count),
            block_count=post.block_count,
            image_count=images,
        )

    def status_label(self, post: BlogPost, has_changes: bool) -> str:
        if post.status == "scheduled" and post.scheduled_at:
            local = post.scheduled_at.astimezone(ZoneInfo(self.settings.timezone))
            return f"Scheduled · {local.day} {local:%b}, {local:%-I:%M %p}"
        if post.status == "published":
            return "Published · unpublished changes" if has_changes else "Published"
        if post.status == "archived":
            return "Archived"
        return "Draft"

    def view(self, post: BlogPost) -> PostView:
        media_ids = [i for i in (post.cover_asset_id, post.og_asset_id) if i]
        media = self.repo.get_media(media_ids) if media_ids else {}
        has_changes = self.has_unpublished_changes(post)
        status = "draft" if post.status == "review" else post.status
        return PostView(
            id=post.id,
            version=post.version,
            title=post.title,
            subtitle=post.subtitle,
            slug=post.slug,
            slug_locked=post.slug_locked,
            content=post.content or {"type": "doc", "content": []},
            excerpt=post.excerpt,
            cover=media.get(post.cover_asset_id) if post.cover_asset_id else None,
            og_image=media.get(post.og_asset_id) if post.og_asset_id else None,
            category=self.categories.get(post.category_id) if post.category_id else None,
            tags=list(post.tags),
            allow_comments=post.allow_comments,
            seo={k: (post.seo or {}).get(k) for k in ("meta_title", "meta_description", "canonical_url")},
            seo_effective=self.seo_effective(post),
            status=status,
            status_label=self.status_label(post, has_changes),
            scheduled_at=post.scheduled_at,
            published_at=post.published_at,
            last_published_at=post.last_published_at,
            has_unpublished_changes=has_changes,
            public_url=self.settings.public_url(post.slug) if post.status == "published" else None,
            schedule_error=post.schedule_error,
            stats=self.stats(post),
            checklist=self.checklist(post),
            author=self.repo.get_author(post.author_id),
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    # ── publishing ───────────────────────────────────────────────────────

    def publish(
        self,
        post: BlogPost,
        actor_id: uuid.UUID | None,
        *,
        trigger: str,
        published_at: datetime.datetime | None = None,
    ) -> BlogPost:
        """Snapshot the working copy as the live revision. Caller holds the row
        lock and has checked the version."""
        checklist = self.checklist(post)
        if not checklist.can_publish:
            raise ChecklistFailedError(checklist)
        first_time = post.published_at is None
        if post.status == "published" and not self.has_unpublished_changes(post):
            raise InvalidStateError("NO_CHANGES", "Nothing to update — the live post is current.")

        previous = (
            self.repo.get_revision(post.id, post.published_revision_id)
            if post.published_revision_id else None
        )
        revision = self.repo.add_revision(
            post_id=post.id,
            kind="publish",
            label="Published" if first_time else "Updated",
            snapshot=self.snapshot(post),
            content_html=post.content_html,
            content_hash=post.content_hash or self.hash_state(self.publishable_state(post, {})),
            word_count=post.word_count,
            created_by=actor_id,
        )
        old_slug = previous.snapshot.get("slug") if previous else None
        if old_slug and old_slug != post.slug:
            self.repo.add_redirect(old_slug, post.id)
        self.repo.delete_redirect(post.slug)

        now = self.clock()
        fields = {
            "status": "published",
            "published_revision_id": revision.id,
            "last_published_at": now,
            "scheduled_at": None,
            "schedule_error": None,
        }
        if first_time:
            fields["published_at"] = published_at or now
        updated = self.repo.update(post.id, post.version, fields)

        self.record(
            "blog_published" if first_time else "blog_updated",
            updated,
            actor_id,
            f"Blog post '{updated.title}' {'published' if first_time else 'updated'}.",
            {"trigger": trigger},
        )
        return updated

    def record(
        self, action: str, post: BlogPost, actor_id: uuid.UUID | None, description: str,
        metadata: dict | None = None,
    ) -> None:
        self.activity.record(
            action_type=action,
            description=description,
            entity_type="blog_post",
            entity_id=post.id,
            entity_title=post.title,
            performed_by=actor_id,
            metadata=metadata,
        )


def _cloudinary_variant(url: str, transform: str) -> str:
    """Insert a Cloudinary transformation after ``/upload/`` (no-op for others)."""
    marker = "/upload/"
    if "res.cloudinary.com" not in url or marker not in url:
        return url
    head, tail = url.split(marker, 1)
    return f"{head}{marker}{transform}/{tail}"


def media_url(media: BlogMedia | None, transform: str | None = None) -> str | None:
    if media is None or not media.url:
        return None
    return _cloudinary_variant(media.url, transform) if transform else media.url

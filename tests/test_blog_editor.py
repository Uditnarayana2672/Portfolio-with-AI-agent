"""Tests for the blog editor: content rules, renderer, workflow and endpoints.

Use cases run against in-memory fake repositories (no DB), so the whole
lifecycle — create → autosave → publish → edit → Update / Discard, schedule →
scheduler — is exercised end to end. Endpoint tests check error mapping.
"""
from __future__ import annotations

import dataclasses
import datetime
import os
import uuid
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "sb_publishable_test")

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_blog_workflow
from app.application.dtos.blog import BlogSettings
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.application.use_cases.blog.posts import CheckBlogSlug, CreateBlogPost, DeleteBlogPost, UpdateBlogPost
from app.application.use_cases.blog.publishing import (
    DiscardBlogChanges,
    PublishBlogPost,
    PublishDuePosts,
    ScheduleBlogPost,
    UnpublishBlogPost,
)
from app.application.use_cases.blog.revisions import CreateBlogRevision, RestoreBlogRevision
from app.domain.blog.content_schema import normalize_document
from app.domain.blog.embeds import resolve_embed
from app.domain.blog.slug import slugify
from app.domain.entities.blog_post import AuthorInfo, BlogCategory, BlogMedia, BlogPost, BlogRevision
from app.domain.exceptions import (
    BlogRuleError,
    ChecklistFailedError,
    InvalidStateError,
    SlugTakenError,
    VersionConflictError,
)
from app.domain.repositories.blog_category_repository import BlogCategoryRepository
from app.domain.repositories.blog_post_repository import BlogPostRepository
from app.infrastructure.persistence.orm.models import UserRole, Users
from app.infrastructure.rendering.tiptap_renderer import TipTapHtmlRenderer
from app.main import app

ADMIN_ID = uuid.UUID("a0000000-0000-0000-0000-0000000000b1")
CATEGORY_ID = uuid.UUID("c0000000-0000-0000-0000-0000000000c1")
IMAGE_ID = uuid.UUID("10000000-0000-0000-0000-0000000000d1")
NOW = datetime.datetime(2026, 11, 3, 9, 0, tzinfo=datetime.timezone.utc)


# ── fakes ────────────────────────────────────────────────────────────────────


class FakeBlogRepo(BlogPostRepository):
    def __init__(self) -> None:
        self.posts: dict[uuid.UUID, BlogPost] = {}
        self.revisions: list[BlogRevision] = []
        self.redirects: dict[str, uuid.UUID] = {}
        self.media = {
            IMAGE_ID: BlogMedia(IMAGE_ID, "https://res.cloudinary.com/x/image/upload/v1/blog/inline/a.png",
                                "blog/inline/a", "image", "cloudinary", 1600, 900, "alt", None),
        }

    def get(self, post_id, *, for_update=False):
        return self.posts.get(post_id)

    def add(self, fields):
        defaults = dict(
            id=uuid.uuid4(), title="", subtitle=None, slug="", slug_locked=False, content={},
            content_html="", content_text="", content_hash=None, excerpt=None, category_id=None,
            tags=[], status="draft", visibility="public", allow_comments=True, seo={},
            author_id=ADMIN_ID, cover_asset_id=None, og_asset_id=None, cover_image_url=None,
            og_image_url=None, word_count=0, block_count=0, read_time=None, version=1,
            published_revision_id=None, scheduled_at=None, published_at=None, last_published_at=None,
            schedule_error=None, created_at=NOW, updated_at=NOW,
        )
        known = {k: v for k, v in fields.items() if k in defaults}
        post = BlogPost(**{**defaults, **known})
        self.posts[post.id] = post
        return post

    def update(self, post_id, expected_version, fields):
        post = self.posts[post_id]
        if expected_version is not None and post.version != expected_version:
            raise VersionConflictError(post.version, post.updated_at)
        known = {k: v for k, v in fields.items() if hasattr(post, k)}
        post = dataclasses.replace(post, **known, version=post.version + 1)
        self.posts[post_id] = post
        return post

    def delete(self, post_id):
        self.posts.pop(post_id)

    def slug_owner(self, slug):
        return next((p.id for p in self.posts.values() if p.slug == slug), None)

    def redirect_owner(self, slug):
        return self.redirects.get(slug)

    def add_redirect(self, old_slug, post_id):
        self.redirects[old_slug] = post_id

    def delete_redirect(self, slug):
        self.redirects.pop(slug, None)

    def due_scheduled_ids(self, limit):
        return [p.id for p in self.posts.values()
                if p.status == "scheduled" and p.scheduled_at <= NOW + datetime.timedelta(days=30)][:limit]

    def add_revision(self, *, post_id, kind, label, snapshot, content_html, content_hash, word_count, created_by):
        rev = BlogRevision(uuid.uuid4(), post_id, kind, label, snapshot, content_html, content_hash,
                           word_count, created_by, "Udit", NOW + datetime.timedelta(seconds=len(self.revisions)))
        self.revisions.append(rev)
        return rev

    def get_revision(self, post_id, revision_id):
        return next((r for r in self.revisions if r.id == revision_id and r.post_id == post_id), None)

    def latest_revision(self, post_id):
        revs = [r for r in self.revisions if r.post_id == post_id]
        return revs[-1] if revs else None

    def list_revisions(self, post_id, *, kind, page, limit):
        revs = [r for r in reversed(self.revisions) if r.post_id == post_id and (not kind or r.kind == kind)]
        return revs[(page - 1) * limit: page * limit], len(revs)

    def prune_revisions(self, post_id, keep, protect):
        pass

    def get_media(self, asset_ids):
        return {i: self.media[i] for i in asset_ids if i in self.media}

    def get_author(self, user_id):
        return AuthorInfo(user_id, "Udit N.")

    def category_exists(self, category_id):
        return category_id == CATEGORY_ID

    def list_tags(self, prefix, limit):
        return []

    def search_link_targets(self, query, limit):
        return []

    def link_target_status(self, kind, target_id):
        return None


class FakeCategories(BlogCategoryRepository):
    def list_with_counts(self):
        return [self.get(CATEGORY_ID)]

    def get(self, category_id):
        if category_id != CATEGORY_ID:
            return None
        return BlogCategory(CATEGORY_ID, "AI & Agents", "ai-agents", None, 1, NOW)

    def find_by_name_or_slug(self, name, slug):
        return None

    def add(self, *, name, slug, description):
        raise NotImplementedError


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    repo = FakeBlogRepo()
    activity = MagicMock()
    clock = Clock()
    wf = BlogPostWorkflow(repo=repo, categories=FakeCategories(), renderer=TipTapHtmlRenderer(),
                          activity=activity, settings=BlogSettings(), clock=clock)
    return wf, repo, activity, clock


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _doc(*nodes) -> dict:
    return {"type": "doc", "content": list(nodes)}


LONG_BODY = _doc(_para(" ".join(["word"] * 60)))
READY = dict(
    title="Building Jerry: a study in style RAG",
    excerpt="How to make a frontier LLM sound like you without training a model from scratch at all.",
    category_id=CATEGORY_ID,
    content=LONG_BODY,
)


def _create_ready(wf) -> uuid.UUID:
    return CreateBlogPost(wf).execute(ADMIN_ID, dict(READY)).id


# ── content schema & renderer ────────────────────────────────────────────────


class TestContent:
    def test_unknown_node_rejected(self):
        with pytest.raises(BlogRuleError) as exc:
            normalize_document(_doc({"type": "script"}))
        assert exc.value.code == "INVALID_CONTENT"

    def test_javascript_link_rejected(self):
        doc = _doc({"type": "paragraph", "content": [
            {"type": "text", "text": "x", "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}]}]})
        with pytest.raises(BlogRuleError) as exc:
            normalize_document(doc)
        assert exc.value.code == "INVALID_LINK"

    def test_unknown_attributes_dropped(self):
        doc, _ = normalize_document(_doc({"type": "heading", "attrs": {"level": 2, "onclick": "x"},
                                          "content": [{"type": "text", "text": "Hi"}]}))
        assert doc["content"][0]["attrs"] == {"level": 2, "numbered": False}

    def test_text_is_escaped(self):
        doc, _ = normalize_document(_doc(_para("<img src=x onerror=alert(1)>")))
        html = TipTapHtmlRenderer().render(doc).html
        assert "<img" not in html and "&lt;img" in html

    def test_numbered_headings_count_within_section(self):
        def h(level, text, numbered=False):
            return {"type": "heading", "attrs": {"level": level, "numbered": numbered},
                    "content": [{"type": "text", "text": text}]}
        doc, _ = normalize_document(_doc(
            h(2, "A"), h(3, "one", True), _para("between"), h(3, "two", True),
            h(2, "B"), h(3, "again", True),
        ))
        toc = TipTapHtmlRenderer().render(doc).toc
        assert [t.number for t in toc] == [None, "1", "2", None, "1"]

    def test_duplicate_heading_ids_are_unique(self):
        h = {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Intro"}]}
        doc, _ = normalize_document(_doc(h, h))
        assert [t.id for t in TipTapHtmlRenderer().render(doc).toc] == ["intro", "intro-2"]

    def test_youtube_src_is_derived_not_trusted(self):
        doc, facts = normalize_document(_doc({"type": "video", "attrs": {
            "source": "youtube", "asset_id": str(IMAGE_ID), "external_id": "dQw4w9WgXcQ",
            "src": "https://evil.example/embed"}}))
        assert doc["content"][0]["attrs"]["src"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        assert str(IMAGE_ID) in facts.asset_ids

    def test_image_without_alt_is_flagged(self):
        _, facts = normalize_document(_doc({"type": "image", "attrs": {
            "asset_id": str(IMAGE_ID), "src": "https://res.cloudinary.com/x/image/upload/a.png"}}))
        assert facts.images_missing_alt == ["content[0]"]

    def test_image_must_come_from_cloudinary(self):
        with pytest.raises(BlogRuleError):
            normalize_document(_doc({"type": "image", "attrs": {
                "asset_id": str(IMAGE_ID), "src": "https://tracker.example/pixel.png"}}))

    def test_embed_resolution(self):
        assert resolve_embed("https://codepen.io/udit/pen/abcXYZ").embed_url.startswith(
            "https://codepen.io/udit/embed/abcXYZ")
        with pytest.raises(BlogRuleError) as exc:
            resolve_embed("https://youtu.be/dQw4w9WgXcQ")
        assert exc.value.code == "UNSUPPORTED_PROVIDER"

    def test_slugify(self):
        assert slugify("Building Jerry: a study in style RAG!") == "building-jerry-a-study-in-style-rag"
        assert slugify("Café déjà vu") == "cafe-deja-vu"
        assert slugify("🚀🚀") == ""


# ── workflow ─────────────────────────────────────────────────────────────────


class TestLifecycle:
    def test_create_requires_title_or_text(self, env):
        wf, *_ = env
        with pytest.raises(BlogRuleError) as exc:
            CreateBlogPost(wf).execute(ADMIN_ID, {"title": "  "})
        assert exc.value.code == "EMPTY_POST"

    def test_create_derives_slug_and_dedupes(self, env):
        wf, *_ = env
        a = CreateBlogPost(wf).execute(ADMIN_ID, {"title": "Hello World"})
        b = CreateBlogPost(wf).execute(ADMIN_ID, {"title": "Hello World"})
        assert (a.slug, b.slug) == ("hello-world", "hello-world-2")
        assert a.status == "draft"

    def test_autosave_version_conflict(self, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 1, {"subtitle": "one"})
        with pytest.raises(VersionConflictError) as exc:
            UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 1, {"subtitle": "two"})
        assert exc.value.current_version == 2

    def test_manual_slug_locks_and_clash_suggests(self, env):
        wf, *_ = env
        CreateBlogPost(wf).execute(ADMIN_ID, {"title": "Taken slug here"})
        post_id = CreateBlogPost(wf).execute(ADMIN_ID, {"title": "Other"}).id
        with pytest.raises(SlugTakenError) as exc:
            UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 1, {"slug": "taken-slug-here"})
        assert exc.value.suggested == "taken-slug-here-2"
        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 1, {"slug": "My Custom Slug"})
        assert res.slug == "my-custom-slug"
        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 2, {"title": "Changed title"})
        assert res.slug == "my-custom-slug"  # locked: doesn't follow the title

    def test_reserved_slug(self, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        with pytest.raises(BlogRuleError) as exc:
            UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 1, {"slug": "admin"})
        assert exc.value.code == "RESERVED_SLUG"

    def test_publish_blocked_by_checklist(self, env):
        wf, *_ = env
        post_id = CreateBlogPost(wf).execute(ADMIN_ID, {"title": "Short"}).id
        with pytest.raises(ChecklistFailedError) as exc:
            PublishBlogPost(wf).execute(post_id, ADMIN_ID, 1)
        failing = {i.key for i in exc.value.checklist.items if i.level == "blocker" and not i.passed}
        assert {"title", "category", "excerpt", "body"} <= failing

    def test_publish_edit_update_discard(self, env):
        wf, repo, activity, _ = env
        post_id = _create_ready(wf)
        view = PublishBlogPost(wf).execute(post_id, ADMIN_ID, 1)
        assert view.status == "published" and not view.has_unpublished_changes
        assert view.public_url == "https://uditnarayana.dev/blog/building-jerry-a-study-in-style-rag"

        # A no-op save keeps the live post current.
        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, view.version, {"title": READY["title"]})
        assert not res.has_unpublished_changes

        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, res.version, {"subtitle": "New subtitle"})
        assert res.has_unpublished_changes

        with pytest.raises(InvalidStateError):
            ScheduleBlogPost(wf).execute(post_id, ADMIN_ID, res.version, NOW + datetime.timedelta(days=1))

        discarded = DiscardBlogChanges(wf).execute(post_id, ADMIN_ID, res.version)
        assert discarded.subtitle is None and not discarded.has_unpublished_changes
        assert any(r.label == "Before discard" for r in repo.revisions)

        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, discarded.version, {"subtitle": "Again"})
        updated = PublishBlogPost(wf).execute(post_id, ADMIN_ID, res.version)
        assert updated.subtitle == "Again" and not updated.has_unpublished_changes
        actions = [c.kwargs["action_type"] for c in activity.record.call_args_list]
        assert actions == ["blog_created", "blog_published", "blog_changes_discarded", "blog_updated"]

    def test_update_without_changes_is_refused(self, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        view = PublishBlogPost(wf).execute(post_id, ADMIN_ID, 1)
        with pytest.raises(InvalidStateError) as exc:
            PublishBlogPost(wf).execute(post_id, ADMIN_ID, view.version)
        assert exc.value.code == "NO_CHANGES"

    def test_slug_change_after_publish_records_redirect(self, env):
        wf, repo, *_ = env
        post_id = _create_ready(wf)
        view = PublishBlogPost(wf).execute(post_id, ADMIN_ID, 1)
        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, view.version, {"title": "A completely new title"})
        assert res.slug == view.slug  # published posts don't auto-follow the title
        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, res.version, {"slug": "new-slug"})
        PublishBlogPost(wf).execute(post_id, ADMIN_ID, res.version)
        assert repo.redirects[view.slug] == post_id

    def test_unpublish_then_delete_is_refused(self, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        view = PublishBlogPost(wf).execute(post_id, ADMIN_ID, 1)
        view = UnpublishBlogPost(wf).execute(post_id, ADMIN_ID, view.version)
        assert view.status == "draft" and view.published_at is not None
        with pytest.raises(InvalidStateError) as exc:
            DeleteBlogPost(wf).execute(post_id, ADMIN_ID, view.version)
        assert exc.value.code == "POST_WAS_PUBLISHED"

    def test_draft_delete(self, env):
        wf, repo, *_ = env
        post_id = _create_ready(wf)
        DeleteBlogPost(wf).execute(post_id, ADMIN_ID, 1)
        assert post_id not in repo.posts


class TestScheduling:
    def test_schedule_rules(self, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        with pytest.raises(BlogRuleError) as exc:
            ScheduleBlogPost(wf).execute(post_id, ADMIN_ID, 1, NOW + datetime.timedelta(minutes=2))
        assert exc.value.code == "SCHEDULE_TOO_SOON"
        with pytest.raises(BlogRuleError) as exc:
            ScheduleBlogPost(wf).execute(post_id, ADMIN_ID, 1, datetime.datetime(2026, 12, 1, 9))
        assert exc.value.code == "NAIVE_DATETIME"
        view = ScheduleBlogPost(wf).execute(post_id, ADMIN_ID, 1, NOW + datetime.timedelta(hours=1))
        assert view.status == "scheduled"
        assert view.status_label == "Scheduled · 3 Nov, 3:30 PM"  # 10:00 UTC in IST

    def test_scheduler_publishes_due_post_with_scheduled_date(self, env):
        wf, _repo, _activity, clock = env
        post_id = _create_ready(wf)
        when = NOW + datetime.timedelta(hours=1)
        ScheduleBlogPost(wf).execute(post_id, ADMIN_ID, 1, when)
        clock.now = when + datetime.timedelta(seconds=30)
        result = PublishDuePosts(wf).execute()
        assert result.published[0]["delay_seconds"] == 30
        post = wf.repo.get(post_id)
        assert post.status == "published" and post.published_at == when

    def test_scheduler_falls_back_to_draft_when_checklist_breaks(self, env):
        wf, repo, activity, clock = env
        post_id = _create_ready(wf)
        when = NOW + datetime.timedelta(hours=1)
        view = ScheduleBlogPost(wf).execute(post_id, ADMIN_ID, 1, when)
        # The excerpt gets wiped after scheduling.
        UpdateBlogPost(wf).execute(post_id, ADMIN_ID, view.version, {"excerpt": None})
        clock.now = when
        result = PublishDuePosts(wf).execute()
        assert result.failed and not result.published
        post = repo.get(post_id)
        assert post.status == "draft" and post.scheduled_at is None
        assert post.schedule_error.startswith("Scheduled publish failed")
        assert activity.record.call_args.kwargs["action_type"] == "blog_schedule_failed"


class TestRevisions:
    def test_save_draft_dedupes_and_restore_keeps_safety_copy(self, env):
        wf, repo, *_ = env
        post_id = _create_ready(wf)
        _rv, created = CreateBlogRevision(wf).execute(post_id, ADMIN_ID, 1, "first")
        _rv2, created2 = CreateBlogRevision(wf).execute(post_id, ADMIN_ID, 1, "again")
        assert created and not created2
        res = UpdateBlogPost(wf).execute(post_id, ADMIN_ID, 1, {"subtitle": "changed"})
        view = RestoreBlogRevision(wf).execute(post_id, _rv.revision.id, ADMIN_ID, res.version)
        assert view.subtitle is None
        assert [r.label for r in repo.revisions] == ["first", "Before restore"]

    def test_check_slug(self, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        result = CheckBlogSlug(wf).execute("Building Jerry: a study in style RAG", None)
        assert not result.available and result.reason == "taken"
        assert result.suggested == "building-jerry-a-study-in-style-rag-2"
        assert CheckBlogSlug(wf).execute("building-jerry-a-study-in-style-rag", post_id).available
        assert CheckBlogSlug(wf).execute("rss", None).reason == "reserved"


# ── HTTP ─────────────────────────────────────────────────────────────────────


def _fake_admin():
    user = MagicMock(spec=Users)
    user.id = ADMIN_ID
    user.role = UserRole.ADMIN
    user.is_blocked = False
    return user


@pytest.fixture
def client(env):
    wf, *_ = env
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_blog_workflow] = lambda: wf
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHttp:
    def test_create_patch_conflict_and_checklist_error(self, client):
        r = client.post("/api/v1/admin/blogs", json={"title": "Draft one"}, headers={"Idempotency-Key": "k1"})
        assert r.status_code == 201
        post = r.json()
        assert post["status_label"] == "Draft" and post["checklist"]["can_publish"] is False
        assert post["created_at"].endswith("Z")

        again = client.post("/api/v1/admin/blogs", json={"title": "Draft one"}, headers={"Idempotency-Key": "k1"})
        assert again.status_code == 200 and again.json()["id"] == post["id"]

        url = f"/api/v1/admin/blogs/{post['id']}"
        assert client.patch(url, json={"version": 1, "subtitle": "s"}).json()["version"] == 2
        r = client.patch(url, json={"version": 1, "subtitle": "x"})
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "VERSION_CONFLICT"
        assert r.json()["detail"]["detail"]["current_version"] == 2

        r = client.post(f"{url}/publish", json={"version": 2})
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "CHECKLIST_FAILED"
        assert r.json()["detail"]["detail"]["checklist"]["blocker_count"] >= 1

    def test_invalid_content_is_422(self, client):
        r = client.post("/api/v1/admin/blogs", json={"title": "x", "content": _doc({"type": "iframe"})})
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "INVALID_CONTENT"

    def test_unknown_post_is_404(self, client):
        r = client.get(f"/api/v1/admin/blogs/{uuid.uuid4()}")
        assert r.status_code == 404 and r.json()["detail"]["error"] == "POST_NOT_FOUND"

    def test_editor_config_lists_blocks(self, client):
        cfg = client.get("/api/v1/admin/blogs/editor-config").json()
        types = {b["type"] for b in cfg["blocks"]}
        assert {"heading", "callout", "table", "imageGallery", "video", "codeBlock"} <= types
        assert cfg["timezone"] == "Asia/Kolkata"

    def test_preview_payload(self, client, env):
        wf, *_ = env
        post_id = _create_ready(wf)
        r = client.get(f"/api/v1/admin/blogs/{post_id}/preview")
        assert r.status_code == 200
        body = r.json()
        assert body["post"]["head"]["json_ld"]["@type"] == "BlogPosting"
        assert body["search_preview"]["url_display"].startswith("uditnarayana.dev › blog ›")
        assert client.get(f"/api/v1/admin/blogs/{post_id}/preview?source=live").status_code == 409

    def test_cron_endpoint_disabled_without_secret(self, client):
        assert client.post("/api/v1/internal/blogs/publish-due").status_code == 404

"""Tests for the Blog Manager: list parameters, facets, bulk archive/delete,
unarchive, and the SQL the list repository builds.

Use cases run against the in-memory fakes from test_blog_editor. The SQL
repository is exercised with a recording session and compiled for the
Postgres dialect, which catches construction errors without a database.
"""
from __future__ import annotations

import dataclasses
import datetime
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from test_blog_editor import ADMIN_ID, CATEGORY_ID, NOW, FakeBlogRepo, FakeCategories, Clock

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_blog_list_repository, get_blog_workflow
from app.application.dtos.blog import BlogSettings, PostListParams
from app.application.use_cases.blog.manager import (
    BulkBlogAction,
    GetBlogStats,
    ListBlogPosts,
    UnarchiveBlogPost,
)
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.domain.entities.blog_post import BlogStatusStats, PostListQuery, PostListRow, SearchTerms
from app.domain.exceptions import BlogRuleError, InvalidStateError
from app.domain.repositories.blog_list_repository import BlogListRepository
from app.infrastructure.persistence.orm.models import UserRole, Users
from app.infrastructure.persistence.repositories.blog_list_repository import SqlAlchemyBlogListRepository
from app.infrastructure.rendering.tiptap_renderer import TipTapHtmlRenderer
from app.main import app

OTHER_ID = uuid.UUID("a0000000-0000-0000-0000-0000000000b2")


# ── fakes ────────────────────────────────────────────────────────────────────


def _row(**over) -> PostListRow:
    base = dict(
        id=uuid.uuid4(), title="Building Jerry", slug="building-jerry", excerpt=None,
        body_start="  How to make a model sound like you.  ", status="published",
        has_unpublished_changes=False, category_id=CATEGORY_ID, category_name="AI & Agents",
        category_slug="ai-agents", tags=["rag"], cover_asset_id=uuid.uuid4(),
        cover_url="https://res.cloudinary.com/x/image/upload/v1/blog/covers/c.png", cover_alt=None,
        read_time=8, word_count=1800, views=12, author_id=ADMIN_ID, author_name="Udit N.", version=3,
        scheduled_at=None, schedule_error=None, published_at=NOW, archived_at=None,
        created_at=NOW, updated_at=NOW,
    )
    return PostListRow(**{**base, **over})


class FakeListRepo(BlogListRepository):
    def __init__(self, rows=None, by_status=None, by_category=None) -> None:
        self.rows = rows or []
        self.by_status = by_status or {}
        self.by_category = by_category or {}
        self.queries: list[PostListQuery] = []

    def list_posts(self, query):
        self.queries.append(query)
        return self.rows, len(self.rows)

    def facet_counts(self, query):
        return self.by_status, self.by_category

    def status_stats(self, author_id, created_since):
        self.created_since = created_since
        return BlogStatusStats({"published": 3, "draft": 2, "scheduled": 1, "archived": 4}, 2, None, 1)


@pytest.fixture
def wf_env():
    repo = FakeBlogRepo()
    activity = MagicMock()
    wf = BlogPostWorkflow(repo=repo, categories=FakeCategories(), renderer=TipTapHtmlRenderer(),
                          activity=activity, settings=BlogSettings(), clock=Clock())
    return wf, repo, activity


def _post(repo: FakeBlogRepo, **fields):
    post = repo.add({"title": fields.pop("title", "A post"), "slug": f"p-{uuid.uuid4().hex[:6]}"})
    post = dataclasses.replace(post, **fields)
    repo.posts[post.id] = post
    return post


# ── list parameters ──────────────────────────────────────────────────────────


def test_list_defaults_to_all_without_archived():
    repo = FakeListRepo()
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams())
    q = repo.queries[0]
    assert q.statuses is None and q.category is None and q.search is None
    assert q.sort == "updated_at" and q.descending is True and q.limit == 20


def test_status_is_repeatable_comma_separated_and_deduplicated():
    repo = FakeListRepo()
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(statuses=["published,draft", "draft", " archived "]))
    assert repo.queries[0].statuses == ("published", "draft", "archived")


@pytest.mark.parametrize("params, field", [
    (PostListParams(statuses=["live"]), "status"),
    (PostListParams(category_id="not-a-uuid"), "category_id"),
    (PostListParams(sort="random"), "sort"),
    (PostListParams(dir="sideways"), "dir"),
    (PostListParams(q="x" * 101), "q"),
])
def test_invalid_params_are_validation_errors(params, field):
    with pytest.raises(BlogRuleError) as exc:
        ListBlogPosts(FakeListRepo()).execute(ADMIN_ID, params)
    assert exc.value.code == "VALIDATION_ERROR"
    assert field in exc.value.detail["fields"]


def test_category_none_and_uuid():
    repo = FakeListRepo()
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(category_id="none"))
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(category_id=str(CATEGORY_ID)))
    assert repo.queries[0].category == "none"
    assert repo.queries[1].category == CATEGORY_ID


@pytest.mark.parametrize("q", ["a", "--", "  ", "?!"])
def test_short_or_punctuation_search_is_ignored(q):
    repo = FakeListRepo()
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(q=q))
    assert repo.queries[0].search is None


def test_search_defaults_to_relevance_and_splits_words():
    repo = FakeListRepo()
    result = ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(q="Graph memry!"))
    q = repo.queries[0]
    assert q.search == SearchTerms(text="Graph memry!", words=("graph", "memry"))
    assert q.sort == "relevance"
    assert result.applied["q"] == "Graph memry!"


def test_relevance_without_search_falls_back_and_title_sorts_ascending():
    repo = FakeListRepo()
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(sort="relevance"))
    ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(sort="title"))
    assert repo.queries[0].sort == "updated_at"
    assert repo.queries[1].sort == "title" and repo.queries[1].descending is False


def test_limit_clamped_and_total_pages():
    repo = FakeListRepo(rows=[_row() for _ in range(3)])
    result = ListBlogPosts(repo).execute(ADMIN_ID, PostListParams(limit=500, page=0))
    assert result.limit == 100 and result.page == 1 and result.total_pages == 1


def test_facets_all_excludes_archived():
    repo = FakeListRepo(by_status={"published": 5, "draft": 2, "archived": 7},
                        by_category={str(CATEGORY_ID): 6, "none": 1})
    facets = ListBlogPosts(repo).execute(ADMIN_ID, PostListParams()).facets
    assert facets["status"] == {"all": 7, "draft": 2, "published": 5, "scheduled": 0, "archived": 7}
    assert facets["category"]["all"] == 7
    assert facets["category"][str(CATEGORY_ID)] == 6 and facets["category"]["none"] == 1


def test_item_mapping_excerpt_fallback_and_cover_thumb():
    row = _row()
    item = ListBlogPosts(FakeListRepo(rows=[row])).execute(ADMIN_ID, PostListParams()).items[0]
    assert item.excerpt == "How to make a model sound like you."
    assert "/upload/c_fill,g_auto,w_128,h_88,f_auto,q_auto/v1/" in item.cover["thumb_url"]
    assert item.category["name"] == "AI & Agents"
    assert item.search is None


def test_stats_total_excludes_archived_and_month_starts_in_ist():
    repo = FakeListRepo()
    clock = lambda: datetime.datetime(2026, 10, 31, 20, 0, tzinfo=datetime.timezone.utc)  # Nov 1, 01:30 IST
    stats = GetBlogStats(repo, BlogSettings(), clock).execute(ADMIN_ID)
    assert stats.total == 6 and stats.archived == 4 and stats.failed_schedules == 1
    assert repo.created_since.month == 11 and repo.created_since.day == 1


# ── bulk archive / delete ────────────────────────────────────────────────────


def test_archive_each_status(wf_env):
    wf, repo, activity = wf_env
    draft = _post(repo)
    live = _post(repo, status="published", published_at=NOW, published_revision_id=uuid.uuid4())
    scheduled = _post(repo, status="scheduled", scheduled_at=NOW + datetime.timedelta(days=1))
    items = [(p.id, p.version) for p in (draft, live, scheduled)]

    result = BulkBlogAction(wf).execute(ADMIN_ID, "archive", items)

    assert sorted(result.succeeded, key=str) == sorted([draft.id, live.id, scheduled.id], key=str)
    for p in (draft, live, scheduled):
        now = repo.posts[p.id]
        assert now.status == "archived" and now.archived_at == NOW and now.scheduled_at is None
    # the live post keeps its history so restore + publish keeps the URL and date
    assert repo.posts[live.id].published_at == NOW
    assert repo.posts[live.id].published_revision_id == live.published_revision_id
    actions = [c.kwargs["action_type"] for c in activity.record.call_args_list]
    assert actions.count("blog_archived") == 3 and actions.count("blog_unscheduled") == 1


def test_archive_partial_failures(wf_env):
    wf, repo, _ = wf_env
    ok = _post(repo)
    stale = _post(repo)
    archived = _post(repo, status="archived", archived_at=NOW)
    foreign = _post(repo, author_id=OTHER_ID)
    missing = uuid.uuid4()
    items = [(ok.id, ok.version), (stale.id, stale.version + 5), (archived.id, archived.version),
             (foreign.id, foreign.version), (missing, 1)]

    result = BulkBlogAction(wf).execute(ADMIN_ID, "archive", items)

    assert result.succeeded == [ok.id] and result.requested == 5
    errors = {f.id: f.error for f in result.failed}
    assert errors == {stale.id: "VERSION_CONFLICT", archived.id: "ALREADY_ARCHIVED",
                      foreign.id: "FORBIDDEN", missing: "POST_NOT_FOUND"}
    assert next(f for f in result.failed if f.id == stale.id).current_version == stale.version
    assert repo.posts[stale.id].status == "draft"


def test_delete_rules(wf_env):
    wf, repo, _ = wf_env
    fresh = _post(repo)
    archived_live = _post(repo, status="archived", archived_at=NOW, published_at=NOW)
    live = _post(repo, status="published", published_at=NOW, published_revision_id=uuid.uuid4())
    unpublished = _post(repo, published_at=NOW)
    scheduled = _post(repo, status="scheduled", scheduled_at=NOW + datetime.timedelta(days=1))
    items = [(p.id, p.version) for p in (fresh, archived_live, live, unpublished, scheduled)]

    result = BulkBlogAction(wf).execute(ADMIN_ID, "delete", items)

    assert set(result.succeeded) == {fresh.id, archived_live.id}
    assert fresh.id not in repo.posts and archived_live.id not in repo.posts
    errors = {f.id: f.error for f in result.failed}
    assert errors == {live.id: "POST_WAS_PUBLISHED", unpublished.id: "POST_WAS_PUBLISHED",
                      scheduled.id: "POST_SCHEDULED"}
    assert live.id in repo.posts and unpublished.id in repo.posts and scheduled.id in repo.posts


@pytest.mark.parametrize("action, items", [
    ("publish", [(uuid.uuid4(), 1)]),
    ("archive", []),
    ("archive", [(uuid.uuid4(), 1) for _ in range(101)]),
])
def test_bulk_rejects_bad_requests(wf_env, action, items):
    wf, _, _ = wf_env
    with pytest.raises(BlogRuleError) as exc:
        BulkBlogAction(wf).execute(ADMIN_ID, action, items)
    assert exc.value.code == "VALIDATION_ERROR"


def test_bulk_merges_duplicate_ids(wf_env):
    wf, repo, _ = wf_env
    p = _post(repo)
    result = BulkBlogAction(wf).execute(ADMIN_ID, "archive", [(p.id, p.version), (p.id, p.version)])
    assert result.requested == 1 and result.succeeded == [p.id]


# ── unarchive ────────────────────────────────────────────────────────────────


def test_unarchive_goes_back_to_draft_and_keeps_history(wf_env):
    wf, repo, activity = wf_env
    p = _post(repo, status="archived", archived_at=NOW, published_at=NOW)
    view = UnarchiveBlogPost(wf).execute(p.id, ADMIN_ID, p.version)
    now = repo.posts[p.id]
    assert view.status == "draft" and now.archived_at is None and now.published_at == NOW
    assert activity.record.call_args.kwargs["metadata"] == {"action": "unarchived"}


def test_unarchive_refuses_non_archived(wf_env):
    wf, repo, _ = wf_env
    p = _post(repo)
    with pytest.raises(InvalidStateError) as exc:
        UnarchiveBlogPost(wf).execute(p.id, ADMIN_ID, p.version)
    assert exc.value.code == "NOT_ARCHIVED"


def test_archived_post_stays_read_only_until_restored(wf_env):
    from app.application.use_cases.blog.posts import UpdateBlogPost

    wf, repo, _ = wf_env
    p = _post(repo)
    BulkBlogAction(wf).execute(ADMIN_ID, "archive", [(p.id, p.version)])
    archived = repo.posts[p.id]
    with pytest.raises(InvalidStateError) as exc:
        UpdateBlogPost(wf).execute(p.id, ADMIN_ID, archived.version, {"title": "x"})
    assert exc.value.code == "POST_ARCHIVED"


# ── SQL construction (compiled for Postgres, no database) ────────────────────


def _compile_all(query: PostListQuery) -> list[str]:
    db = MagicMock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []
    repo = SqlAlchemyBlogListRepository(db)
    repo.list_posts(query)
    repo.facet_counts(query)
    stmts = [c.args[0] for c in db.scalar.call_args_list + db.execute.call_args_list]
    return [str(s.compile(dialect=postgresql.dialect())) for s in stmts]


def test_list_sql_without_search():
    sql = _compile_all(PostListQuery(author_id=ADMIN_ID))
    joined = "\n".join(sql)
    assert "blog_posts.status != %(status_1)s" in joined
    assert "search_vector" not in joined
    assert "ORDER BY blog_posts.updated_at DESC NULLS LAST, blog_posts.id" in joined


def test_list_sql_with_search_filters_and_title_sort():
    query = PostListQuery(
        author_id=ADMIN_ID, statuses=("draft", "archived"), category="none",
        search=SearchTerms("graph memry", ("graph", "memry")), sort="title", descending=False,
    )
    joined = "\n".join(_compile_all(query))
    assert "blog_posts.search_vector @@ to_tsquery" in joined
    assert "websearch_to_tsquery" in joined and "word_similarity" in joined and "ts_headline" in joined
    assert "blog_posts.category_id IS NULL" in joined
    assert "lower(nullif(blog_posts.title" in joined


def test_list_sql_relevance_order():
    query = PostListQuery(author_id=ADMIN_ID, search=SearchTerms("rag", ("rag",)), sort="relevance")
    list_sql = _compile_all(query)[1]
    assert "ts_rank_cd" in list_sql.split("ORDER BY", 1)[1]


def test_search_match_columns_are_boolean():
    # `tags && …` and `@@` inherit the left operand's type (ARRAY / TSVECTOR)
    # unless marked as comparisons; SQLAlchemy then tries to unpack the
    # returned bool as an array and every search 500s.
    from sqlalchemy import Boolean
    from app.infrastructure.persistence.repositories.blog_list_repository import _Search

    s = _Search(SearchTerms("galaxy ultra", ("galaxy", "ultra")))
    for expr in (s.tag_hit, s.title_words_hit, s.text_hit, s.condition):
        assert isinstance(expr.type, Boolean), expr


def test_prefix_query_only_contains_sanitized_words():
    db = MagicMock()
    db.scalar.return_value = 0
    SqlAlchemyBlogListRepository(db).list_posts(
        PostListQuery(author_id=ADMIN_ID, search=SearchTerms("rag & (x:*", ("rag", "x")))
    )
    params = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect()).params
    assert "rag & x:*" in params.values()


# ── endpoints ────────────────────────────────────────────────────────────────


@pytest.fixture
def client(wf_env):
    wf, repo, _ = wf_env
    admin = MagicMock(spec=Users)
    admin.id, admin.role, admin.is_blocked = ADMIN_ID, UserRole.ADMIN, False
    list_repo = FakeListRepo(rows=[_row()])
    app.dependency_overrides[get_current_admin] = lambda: admin
    app.dependency_overrides[get_blog_workflow] = lambda: wf
    app.dependency_overrides[get_blog_list_repository] = lambda: list_repo
    yield TestClient(app), repo, list_repo
    app.dependency_overrides.clear()


def test_list_endpoint(client):
    c, _, list_repo = client
    r = c.get("/api/v1/admin/blogs?status=draft&status=published&q=jerry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"][0]["title"] == "Building Jerry"
    assert body["items"][0]["published_at"].endswith("Z")
    assert body["applied"]["status"] == ["draft", "published"]
    assert list_repo.queries[0].search.words == ("jerry",)


def test_list_endpoint_validation_envelope(client):
    c, _, _ = client
    r = c.get("/api/v1/admin/blogs?status=live")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "VALIDATION_ERROR"


def test_stats_endpoint_is_not_shadowed_by_post_id(client):
    c, _, _ = client
    r = c.get("/api/v1/admin/blogs/stats")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 6


def test_bulk_and_unarchive_endpoints(client):
    c, repo, _ = client
    p = _post(repo)
    r = c.post("/api/v1/admin/blogs/bulk", json={"action": "archive", "items": [{"id": str(p.id), "version": p.version}]})
    assert r.status_code == 200, r.text
    assert r.json()["succeeded"] == [str(p.id)]
    version = repo.posts[p.id].version

    r = c.post("/api/v1/admin/blogs/bulk", json={"action": "feature", "items": [{"id": str(p.id), "version": version}]})
    assert r.status_code == 422

    r = c.post(f"/api/v1/admin/blogs/{p.id}/unarchive", json={"version": version})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"

    r = c.post(f"/api/v1/admin/blogs/{p.id}/unarchive", json={"version": repo.posts[p.id].version})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "NOT_ARCHIVED"


# ── media sizes (Plan §8) ────────────────────────────────────────────────────

_IMG = "https://res.cloudinary.com/x/image/upload/v1/blog/inline/a.png"


def _render_one(node: dict) -> str:
    from app.domain.blog.content_schema import normalize_document

    doc, _ = normalize_document({"type": "doc", "content": [node]})
    return TipTapHtmlRenderer().render(doc).html


def _image(**attrs) -> dict:
    return {"type": "image", "attrs": {"asset_id": str(uuid.uuid4()), "src": _IMG, "alt": "a", **attrs}}


def test_image_medium_is_capped_and_has_zoom_source():
    html = _render_one(_image(size="medium", width=1600, height=900))
    assert 'class="bp-image bp-image--medium" style="max-width:560px"' in html
    assert 'sizes="(max-width: 600px) 100vw, 560px"' in html
    assert 'data-zoom-src="https://res.cloudinary.com/x/image/upload/f_auto,q_auto,w_2000,c_limit/v1/' in html
    assert '<div class="bp-image__frame">' in html


def test_small_file_is_never_upscaled():
    html = _render_one(_image(size="medium", width=300, height=200))
    assert 'style="max-width:300px"' in html


def test_existing_posts_keep_normal_and_unknown_size_falls_back():
    assert "bp-image--normal" in _render_one(_image(width=1600, height=900))
    assert "bp-image--normal" in _render_one(_image(size="huge", width=1600, height=900))
    assert 'bp-image--full"><div' in _render_one(_image(size="full", width=1600, height=900))


def test_video_size_class():
    node = {"type": "video", "attrs": {"source": "youtube", "external_id": "dQw4w9WgXcQ",
                                       "asset_id": str(uuid.uuid4()), "size": "small"}}
    html = _render_one(node)
    assert 'class="bp-video bp-video--small bp-video--youtube" style="max-width:360px"' in html

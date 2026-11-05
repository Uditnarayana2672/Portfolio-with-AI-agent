"""Tests for the admin Overview APIs: activity stream and portfolio content."""
from __future__ import annotations

import copy
import datetime
import json
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies.auth import get_current_admin, get_current_user
from app.api.v1.dependencies.providers import (
    get_get_portfolio_content,
    get_list_recent_activity,
    get_public_site_repository,
    get_update_portfolio_content,
)
from app.api.v1.schemas.portfolio import PortfolioDocument
from app.application.use_cases.activity.list_recent_activity import ListRecentActivity
from app.application.use_cases.portfolio.portfolio_content import GetPortfolioContent, UpdatePortfolioContent
from app.domain.entities.portfolio_content import PortfolioContent
from app.domain.exceptions import PortfolioContentNotFoundError, VersionConflictError
from app.domain.portfolio_document import upgrade_document
from app.domain.repositories.activity_log_repository import ActivityEntry
from app.infrastructure.persistence.orm.models import UserRole
from app.main import app

_NOW = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.timezone.utc)
_ADMIN = SimpleNamespace(id=uuid.uuid4(), name="Udit Narayana")

_SEED_SQL = (Path(__file__).resolve().parents[1] / "supabase/migrations/007_portfolio_content.sql").read_text()
SEED = upgrade_document(json.loads(re.search(r"\$seed\$(.*)\$seed\$", _SEED_SQL, re.S).group(1)))


def _doc(content: dict | None = None, version: int = 1) -> PortfolioContent:
    return PortfolioContent(
        content=copy.deepcopy(content or SEED),
        version=version,
        updated_at=_NOW,
        updated_by_name="Udit Narayana",
    )


def _content(**overrides) -> dict:
    content = copy.deepcopy(SEED)
    content.update(overrides)
    return content


class _FakeRepo:
    """In-memory repository with the same atomic version rule as the real one."""

    def __init__(self, document: PortfolioContent | None = None) -> None:
        self.document = document
        self.update_calls = 0

    def get(self) -> PortfolioContent | None:
        return self.document

    def update(self, *, expected_version: int, content: dict, updated_by: uuid.UUID) -> PortfolioContent | None:
        self.update_calls += 1
        if self.document is None or self.document.version != expected_version:
            return None
        self.document = _doc(content, expected_version + 1)
        return self.document


@pytest.fixture
def repo() -> _FakeRepo:
    return _FakeRepo(_doc())


@pytest.fixture
def activity() -> Mock:
    return Mock()


@pytest.fixture
def client(repo: _FakeRepo, activity: Mock):
    app.dependency_overrides[get_current_admin] = lambda: _ADMIN
    app.dependency_overrides[get_get_portfolio_content] = lambda: GetPortfolioContent(repo)
    app.dependency_overrides[get_update_portfolio_content] = lambda: UpdatePortfolioContent(repo, activity)
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── seed ─────────────────────────────────────────────────────────────────────


def test_seed_is_valid_and_saves_unchanged():
    assert PortfolioDocument.model_validate(SEED).model_dump(mode="json") == SEED


def test_seed_has_all_jobs_in_order():
    assert [j["company"] for j in SEED["experience"]] == ["IBM", "Neudesic", "Flipkart", "Skillvertex"]


# ── load ─────────────────────────────────────────────────────────────────────


def test_admin_get_returns_version_and_content(client):
    res = client.get("/api/v1/admin/portfolio-content")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 1
    assert body["updated_at"] == "2026-11-05T12:00:00Z"
    assert body["updated_by_name"] == "Udit Narayana"
    assert body["content"]["hero"]["headline_accent"] == "And ships."


def test_admin_get_missing_seed_is_404(client, repo):
    repo.document = None
    res = client.get("/api/v1/admin/portfolio-content")
    assert res.status_code == 404
    assert res.json()["detail"]["error"] == "CONTENT_NOT_FOUND"


# ── save ─────────────────────────────────────────────────────────────────────


def test_save_bumps_version_and_records_activity(client, activity):
    hero = {**SEED["hero"], "headline_accent": "And ships it."}
    tech = SEED["tech"][:3]
    res = client.put("/api/v1/admin/portfolio-content", json={"version": 1, "content": _content(hero=hero, tech=tech)})
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 2
    assert body["changed_sections"] == ["hero", "tech"]
    assert body["content"]["hero"]["headline_accent"] == "And ships it."
    kwargs = activity.record.call_args.kwargs
    assert kwargs["action_type"] == "portfolio_updated"
    assert kwargs["description"] == "Portfolio content updated: hero, tech."
    assert kwargs["entity_type"] == "portfolio"
    assert kwargs["performed_by"] == _ADMIN.id


def test_save_without_changes_keeps_version_and_logs_nothing(client, repo, activity):
    res = client.put("/api/v1/admin/portfolio-content", json={"version": 1, "content": _content()})
    assert res.status_code == 200
    assert res.json()["version"] == 1
    assert res.json()["changed_sections"] == []
    assert repo.update_calls == 0
    activity.record.assert_not_called()


def test_stale_version_is_rejected_and_nothing_written(client, repo, activity):
    repo.document = _doc(version=3)
    res = client.put("/api/v1/admin/portfolio-content", json={"version": 2, "content": _content(tech=[])})
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["error"] == "VERSION_CONFLICT"
    assert detail["detail"]["current_version"] == 3
    assert repo.update_calls == 0
    activity.record.assert_not_called()


def test_losing_a_race_after_the_check_is_a_conflict(activity):
    repo = _FakeRepo(_doc())
    repo.update = Mock(return_value=None)
    with pytest.raises(VersionConflictError):
        UpdatePortfolioContent(repo, activity).execute(
            expected_version=1, content=_content(tech=[]), actor_id=_ADMIN.id
        )
    activity.record.assert_not_called()


def test_save_missing_seed_raises(activity):
    with pytest.raises(PortfolioContentNotFoundError):
        UpdatePortfolioContent(_FakeRepo(None), activity).execute(
            expected_version=1, content=_content(), actor_id=_ADMIN.id
        )


def _with_tech(**changes) -> dict:
    tech = copy.deepcopy(SEED["tech"])
    tech[3].update(changes)
    return _content(tech=tech)


def _with_job(**changes) -> dict:
    jobs = copy.deepcopy(SEED["experience"])
    jobs[1].update(changes)
    return _content(experience=jobs)


def _with_url(url: str) -> dict:
    hero = copy.deepcopy(SEED["hero"])
    hero["portrait"] = {"url": url, "alt": "Udit", "media_asset_id": None}
    return _content(hero=hero)


@pytest.mark.parametrize(
    ("content", "path"),
    [
        (_with_tech(level="guru"), "tech[3].level"),
        (_with_tech(categories=[]), "tech[3].categories"),
        (_with_tech(categories=["mobile"]), "tech[3].categories[0]"),
        (_with_tech(logo_slug="Bad Slug!"), "tech[3].logo_slug"),
        (_with_tech(extra_field=1), "tech[3].extra_field"),
        (_with_tech(name="  "), "tech[3].name"),
        (_with_job(end_year=2000), "experience[1]"),
        (_with_url("javascript:alert(1)"), "hero.portrait.url"),
        (_with_url("http://insecure.example"), "hero.portrait.url"),
        (_content(tech=[SEED["tech"][0], SEED["tech"][0]]), "tech"),
        (_content(tech=[{**SEED["tech"][0], "id": f"x{i}"} for i in range(61)]), "tech"),
        (_content(hero={**SEED["hero"], "headline": "x" * 121}), "hero.headline"),
        (_content(about={**SEED["about"], "today": "x" * 601}), "about.today"),
        ({k: v for k, v in SEED.items() if k != "skills"}, "skills"),
        (_content(surprise={}), "surprise"),
    ],
)
def test_invalid_content_reports_the_field(client, repo, content, path):
    res = client.put("/api/v1/admin/portfolio-content", json={"version": 1, "content": content})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "INVALID_CONTENT"
    assert path in [f["path"] for f in detail["detail"]["fields"]]
    assert repo.update_calls == 0


def test_oversized_document_is_413(client):
    res = client.put(
        "/api/v1/admin/portfolio-content",
        json={"version": 1, "content": _content(padding="x" * (65 * 1024))},
    )
    assert res.status_code == 413
    assert res.json()["detail"]["error"] == "CONTENT_TOO_LARGE"


# ── access ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/activity"),
        ("get", "/api/v1/admin/portfolio-content"),
        ("put", "/api/v1/admin/portfolio-content"),
    ],
)
def test_admin_routes_require_a_token(method, path):
    res = TestClient(app).request(method, path)
    assert res.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/activity"),
        ("get", "/api/v1/admin/portfolio-content"),
        ("put", "/api/v1/admin/portfolio-content"),
    ],
)
def test_admin_routes_reject_non_admins(method, path):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.VIEWER)
    try:
        res = TestClient(app).request(method, path)
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 403


def test_public_read_needs_no_login_and_hides_edit_details(repo):
    app.dependency_overrides[get_get_portfolio_content] = lambda: GetPortfolioContent(repo)
    site = Mock()
    site.list_public_projects.return_value = []
    app.dependency_overrides[get_public_site_repository] = lambda: site
    try:
        res = TestClient(app).get("/api/v1/portfolio-content")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    assert res.headers["cache-control"] == "public, max-age=60"
    assert set(res.json()) == {"updated_at", "content"}


# ── activity ─────────────────────────────────────────────────────────────────


def _entry(**overrides) -> ActivityEntry:
    defaults = {
        "id": uuid.uuid4(),
        "action_type": "blog_updated",
        "description": "Blog post updated.",
        "entity_type": "blog_post",
        "entity_id": uuid.uuid4(),
        "entity_title": "Post",
        "performed_by": _ADMIN.id,
        "created_at": _NOW,
        "entity_exists": True,
    }
    return ActivityEntry(**{**defaults, **overrides})


def test_activity_maps_categories_and_links():
    project, blog, media = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = Mock()
    repo.list_recent.return_value = [
        _entry(entity_type="project", entity_id=project),
        _entry(entity_type="blog_post", entity_id=blog),
        _entry(entity_type="media_asset", entity_id=media),
        _entry(entity_type="portfolio", entity_id=None, entity_exists=False),
        _entry(entity_type=None, entity_id=None, entity_exists=False),
    ]
    views = ListRecentActivity(repo).execute(5)
    assert [v.category for v in views] == ["project", "blog", "media", "portfolio", "other"]
    assert [v.link for v in views] == [
        f"/admin/projects/{project}/edit",
        f"/admin/blogs/{blog}/edit",
        "/admin/media",
        None,
        None,
    ]
    repo.list_recent.assert_called_once_with(5)


def test_activity_link_is_null_for_deleted_items():
    repo = Mock()
    repo.list_recent.return_value = [_entry(entity_exists=False)]
    assert ListRecentActivity(repo).execute(1)[0].link is None


def test_activity_actor_you_or_system():
    repo = Mock()
    repo.list_recent.return_value = [_entry(), _entry(performed_by=None)]
    assert [v.actor for v in ListRecentActivity(repo).execute(2)] == ["you", "system"]


@pytest.fixture
def activity_client():
    repo = Mock()
    repo.list_recent.return_value = [_entry()]
    app.dependency_overrides[get_current_admin] = lambda: _ADMIN
    app.dependency_overrides[get_list_recent_activity] = lambda: ListRecentActivity(repo)
    yield TestClient(app), repo
    app.dependency_overrides.clear()


def test_activity_endpoint_defaults_to_20(activity_client):
    client, repo = activity_client
    res = client.get("/api/v1/admin/activity")
    assert res.status_code == 200
    repo.list_recent.assert_called_once_with(20)
    item = res.json()["items"][0]
    assert item["category"] == "blog"
    assert item["created_at"] == "2026-11-05T12:00:00Z"


@pytest.mark.parametrize("limit", [0, 51])
def test_activity_limit_out_of_range_is_422(activity_client, limit):
    client, _ = activity_client
    assert client.get(f"/api/v1/admin/activity?limit={limit}").status_code == 422

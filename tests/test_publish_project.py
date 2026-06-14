"""Tests for POST /api/v1/admin/projects/{id}/publish.

Dependencies are overridden so no real DB or Supabase project is needed.
The auth dependency is stubbed with a fake admin; PublishProject is either a
real instance wired to mock repositories (logic tests) or a MagicMock (HTTP
error-mapping tests).
"""
from __future__ import annotations

import datetime
import os
import uuid
from unittest.mock import MagicMock

# ── fake environment — must be set before the app module is imported ──────────
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "sb_publishable_test")
os.environ.setdefault("SUPABASE_JWT_AUDIENCE", "authenticated")

import pytest
from fastapi.testclient import TestClient

from app.application.dtos.project import PublishProjectCommand, PublishProjectResult
from app.application.use_cases.projects.publish_project import PublishProject
from app.domain.entities.block import Block
from app.domain.entities.project import Project
from app.domain.exceptions import NotFoundError, PermissionError, PublishBlockedError
from app.infrastructure.persistence.orm.models import UserRole, Users
from app.main import app
from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_publish_project

# ── shared fixtures ───────────────────────────────────────────────────────────

ADMIN_ID = uuid.UUID("a0000000-0000-0000-0000-000000000002")
PROJECT_ID = uuid.UUID("c3d4e5f6-2222-2222-2222-000000000002")
NOW = datetime.datetime(2026, 6, 14, 12, 0, 0, tzinfo=datetime.timezone.utc)
URL = f"/api/v1/admin/projects/{PROJECT_ID}/publish"


def _fake_admin():
    user = MagicMock(spec=Users)
    user.id = ADMIN_ID
    user.role = UserRole.ADMIN
    user.is_blocked = False
    return user


def _fake_project(**overrides) -> Project:
    defaults = dict(
        id=PROJECT_ID,
        title="My Portfolio Project",
        slug="my-portfolio-project",
        excerpt=None,
        thumbnail_url=None,
        tech_stack=[],
        template_id="narrative",
        github_url=None,
        demo_url=None,
        status="draft",
        visibility="public",
        is_featured=False,
        views=0,
        seo={"meta_title": "My Portfolio Project | SEO"},
        author_id=ADMIN_ID,
        published_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return Project(**defaults)


def _fake_block() -> Block:
    return Block(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        block_type="hero",
        position=0,
        config={"heading": "Hello"},
        created_at=NOW,
        updated_at=NOW,
    )


def _make_real_use_case(
    project: Project | None = None,
    blocks: list[Block] | None = None,
    published_project: Project | None = None,
) -> PublishProject:
    repo = MagicMock()
    activity = MagicMock()

    if project is None:
        repo.get_with_blocks.return_value = None
    else:
        repo.get_with_blocks.return_value = (project, blocks or [])

    if published_project is not None:
        repo.publish.return_value = published_project

    return PublishProject(repo=repo, activity=activity)


def _client_with(use_case_factory) -> TestClient:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_publish_project] = use_case_factory
    return TestClient(app, raise_server_exceptions=False)


def _cleanup():
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_publish_project, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════════════

class TestHappyPath:
    def teardown_method(self):
        _cleanup()

    def test_publish_with_blocks_returns_200(self):
        project = _fake_project()
        published = _fake_project(status="published", published_at=NOW)
        uc = _make_real_use_case(
            project=project,
            blocks=[_fake_block()],
            published_project=published,
        )
        client = _client_with(lambda: uc)
        resp = client.post(URL)
        assert resp.status_code == 200

    def test_response_contains_expected_fields(self):
        project = _fake_project()
        published = _fake_project(status="published", published_at=NOW)
        uc = _make_real_use_case(
            project=project,
            blocks=[_fake_block()],
            published_project=published,
        )
        client = _client_with(lambda: uc)
        body = client.post(URL).json()
        assert body["id"] == str(PROJECT_ID)
        assert body["slug"] == "my-portfolio-project"
        assert body["status"] == "published"
        assert body["url"] == "/projects/my-portfolio-project"
        assert "published_at" in body

    def test_activity_is_recorded_on_publish(self):
        project = _fake_project()
        published = _fake_project(status="published", published_at=NOW)
        repo = MagicMock()
        repo.get_with_blocks.return_value = (project, [_fake_block()])
        repo.publish.return_value = published
        activity = MagicMock()
        uc = PublishProject(repo=repo, activity=activity)
        client = _client_with(lambda: uc)
        client.post(URL)
        activity.record.assert_called_once()
        kwargs = activity.record.call_args.kwargs
        assert kwargs["action_type"] == "project_published"
        assert kwargs["entity_id"] == PROJECT_ID
        _cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. IDEMPOTENT — already published
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotent:
    def teardown_method(self):
        _cleanup()

    def test_already_published_returns_200(self):
        project = _fake_project(status="published", published_at=NOW)
        uc = _make_real_use_case(project=project, blocks=[_fake_block()])
        client = _client_with(lambda: uc)
        resp = client.post(URL)
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    def test_already_published_does_not_call_publish(self):
        project = _fake_project(status="published", published_at=NOW)
        repo = MagicMock()
        repo.get_with_blocks.return_value = (project, [_fake_block()])
        activity = MagicMock()
        uc = PublishProject(repo=repo, activity=activity)
        client = _client_with(lambda: uc)
        client.post(URL)
        repo.publish.assert_not_called()
        activity.record.assert_not_called()
        _cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PUBLISH BLOCKED (422)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublishBlocked:
    def teardown_method(self):
        _cleanup()

    def test_zero_blocks_returns_422(self):
        project = _fake_project()
        uc = _make_real_use_case(project=project, blocks=[])
        client = _client_with(lambda: uc)
        resp = client.post(URL)
        assert resp.status_code == 422

    def test_zero_blocks_returns_publish_blocked_code(self):
        project = _fake_project()
        uc = _make_real_use_case(project=project, blocks=[])
        client = _client_with(lambda: uc)
        body = client.post(URL).json()
        assert body["code"] == "PUBLISH_BLOCKED"
        assert "At least 1 content block is required" in body["issues"]

    def test_missing_meta_title_is_blocked(self):
        project = _fake_project(seo={})
        uc = _make_real_use_case(project=project, blocks=[_fake_block()])
        client = _client_with(lambda: uc)
        body = client.post(URL).json()
        assert body["code"] == "PUBLISH_BLOCKED"
        assert any("Meta title" in issue for issue in body["issues"])

    def test_blank_title_is_blocked(self):
        project = _fake_project(title="   ")
        uc = _make_real_use_case(project=project, blocks=[_fake_block()])
        client = _client_with(lambda: uc)
        body = client.post(URL).json()
        assert body["code"] == "PUBLISH_BLOCKED"
        assert any("Title" in issue for issue in body["issues"])

    def test_multiple_issues_all_returned(self):
        # No title, no blocks, no meta_title → 3 issues
        project = _fake_project(title="", seo={})
        uc = _make_real_use_case(project=project, blocks=[])
        client = _client_with(lambda: uc)
        body = client.post(URL).json()
        assert body["code"] == "PUBLISH_BLOCKED"
        assert len(body["issues"]) == 3

    def test_detail_is_first_issue(self):
        project = _fake_project(seo={})
        uc = _make_real_use_case(project=project, blocks=[_fake_block()])
        client = _client_with(lambda: uc)
        body = client.post(URL).json()
        assert body["detail"] == body["issues"][0]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NOT FOUND / PERMISSION
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotFoundAndPermission:
    def teardown_method(self):
        _cleanup()

    def test_unknown_project_returns_404(self):
        uc = _make_real_use_case(project=None)
        client = _client_with(lambda: uc)
        resp = client.post(URL)
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "PROJECT_NOT_FOUND"

    def test_wrong_owner_returns_403(self):
        project = _fake_project(author_id=uuid.uuid4())
        uc = _make_real_use_case(project=project, blocks=[_fake_block()])
        client = _client_with(lambda: uc)
        resp = client.post(URL)
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "FORBIDDEN"

    def test_malformed_uuid_returns_422(self):
        client = _client_with(lambda: MagicMock(spec=PublishProject))
        resp = client.post("/api/v1/admin/projects/not-a-uuid/publish")
        assert resp.status_code == 422
        _cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. USE-CASE UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublishProjectUseCase:
    def _build(
        self,
        project: Project | None = None,
        blocks: list[Block] | None = None,
        published_project: Project | None = None,
    ) -> tuple[PublishProject, MagicMock, MagicMock]:
        repo = MagicMock()
        activity = MagicMock()
        if project is None:
            repo.get_with_blocks.return_value = None
        else:
            repo.get_with_blocks.return_value = (project, blocks or [])
        if published_project is not None:
            repo.publish.return_value = published_project
        return PublishProject(repo=repo, activity=activity), repo, activity

    def _cmd(self, author_id: uuid.UUID = ADMIN_ID) -> PublishProjectCommand:
        return PublishProjectCommand(project_id=PROJECT_ID, author_id=author_id)

    def test_raises_not_found_for_missing_project(self):
        uc, _, _ = self._build(project=None)
        with pytest.raises(NotFoundError):
            uc.execute(self._cmd())

    def test_raises_permission_error_for_wrong_author(self):
        project = _fake_project(author_id=uuid.uuid4())
        uc, _, _ = self._build(project=project)
        with pytest.raises(PermissionError):
            uc.execute(self._cmd())

    def test_raises_publish_blocked_for_zero_blocks(self):
        project = _fake_project()
        uc, _, _ = self._build(project=project, blocks=[])
        with pytest.raises(PublishBlockedError) as exc_info:
            uc.execute(self._cmd())
        assert any("block" in issue.lower() for issue in exc_info.value.issues)

    def test_raises_publish_blocked_for_missing_meta_title(self):
        project = _fake_project(seo={})
        uc, _, _ = self._build(project=project, blocks=[_fake_block()])
        with pytest.raises(PublishBlockedError) as exc_info:
            uc.execute(self._cmd())
        assert any("Meta title" in issue for issue in exc_info.value.issues)

    def test_idempotent_already_published_skips_write(self):
        project = _fake_project(status="published", published_at=NOW)
        uc, repo, activity = self._build(project=project, blocks=[_fake_block()])
        result = uc.execute(self._cmd())
        assert result.status == "published"
        repo.publish.assert_not_called()
        activity.record.assert_not_called()

    def test_calls_repo_publish_on_success(self):
        project = _fake_project()
        published = _fake_project(status="published", published_at=NOW)
        uc, repo, _ = self._build(
            project=project, blocks=[_fake_block()], published_project=published
        )
        uc.execute(self._cmd())
        repo.publish.assert_called_once_with(PROJECT_ID)

    def test_returns_publish_project_result(self):
        project = _fake_project()
        published = _fake_project(status="published", published_at=NOW)
        uc, _, _ = self._build(
            project=project, blocks=[_fake_block()], published_project=published
        )
        result = uc.execute(self._cmd())
        assert isinstance(result, PublishProjectResult)
        assert result.status == "published"
        assert result.published_at == NOW

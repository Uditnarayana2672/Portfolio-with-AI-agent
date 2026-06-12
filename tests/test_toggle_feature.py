"""End-to-end tests for API 8 — PATCH /api/v1/admin/projects/{id}/feature.

Dependencies are overridden so no real DB or Supabase project is needed.
The auth dependency is stubbed with a fake admin; the ToggleFeature use case
is either a real instance wired to mock repositories (logic tests) or a
MagicMock (HTTP-mapping tests).
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

from app.application.dtos.project import (
    MAX_FEATURED_PROJECTS,
    ToggleFeatureCommand,
    ToggleFeatureResult,
)
from app.application.use_cases.projects.toggle_feature import ToggleFeature
from app.domain.entities.project import Project
from app.domain.exceptions import (
    FeaturedLimitError,
    NotFoundError,
    PermissionError,
)
from app.infrastructure.persistence.orm.models import UserRole, Users
from app.main import app
from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_toggle_feature

# ── shared fixtures ───────────────────────────────────────────────────────────

ADMIN_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("c3d4e5f6-1111-1111-1111-000000000001")
NOW = datetime.datetime(2026, 6, 12, 10, 10, 0, tzinfo=datetime.timezone.utc)
URL = f"/api/v1/admin/projects/{PROJECT_ID}/feature"


def _fake_admin():
    user = MagicMock(spec=Users)
    user.id = ADMIN_ID
    user.role = UserRole.ADMIN
    user.is_blocked = False
    return user


def _fake_project(**overrides) -> Project:
    defaults = dict(
        id=PROJECT_ID,
        title="Test Project",
        slug="test-project",
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
        seo={},
        author_id=ADMIN_ID,
        published_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return Project(**defaults)


def _make_real_use_case(
    project: Project | None = None,
    *,
    featured_others: int = 0,
    updated_is_featured: bool | None = None,
) -> ToggleFeature:
    repo = MagicMock()
    activity = MagicMock()

    if project is None:
        repo.get_with_blocks.return_value = None
    else:
        repo.get_with_blocks.return_value = (project, [])

    repo.count_featured_excluding.return_value = featured_others

    if project is not None:
        target_state = updated_is_featured if updated_is_featured is not None else (not project.is_featured)
        updated_project = _fake_project(
            id=project.id, author_id=project.author_id, is_featured=target_state
        )
        repo.update.return_value = (updated_project, [])

    return ToggleFeature(repo=repo, activity=activity)


def _client_with(use_case_factory) -> TestClient:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_toggle_feature] = use_case_factory
    return TestClient(app, raise_server_exceptions=False)


def _cleanup():
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_toggle_feature, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════════════

class TestHappyPath:
    def teardown_method(self):
        _cleanup()

    def test_feature_a_project_returns_200(self):
        project = _fake_project(is_featured=False)
        uc = _make_real_use_case(project, featured_others=0, updated_is_featured=True)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(PROJECT_ID)
        assert body["is_featured"] is True

    def test_response_only_has_id_and_is_featured(self):
        project = _fake_project(is_featured=False)
        uc = _make_real_use_case(project, updated_is_featured=True)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert set(resp.json().keys()) == {"id", "is_featured"}

    def test_unfeature_a_project_returns_200(self):
        project = _fake_project(is_featured=True)
        uc = _make_real_use_case(project, updated_is_featured=False)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": False})
        assert resp.status_code == 200
        assert resp.json()["is_featured"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. NO-OP CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoOp:
    def teardown_method(self):
        _cleanup()

    def test_setting_false_when_already_false_returns_200(self):
        project = _fake_project(is_featured=False)
        uc = _make_real_use_case(project)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": False})
        assert resp.status_code == 200
        assert resp.json()["is_featured"] is False

    def test_setting_true_when_already_true_returns_200(self):
        project = _fake_project(is_featured=True)
        uc = _make_real_use_case(project)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 200
        assert resp.json()["is_featured"] is True

    def test_noop_does_not_write_or_count(self):
        """An already-featured project re-asserted true must NOT trip the cap."""
        project = _fake_project(is_featured=True)
        repo = MagicMock()
        repo.get_with_blocks.return_value = (project, [])
        activity = MagicMock()
        uc = ToggleFeature(repo=repo, activity=activity)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 200
        repo.update.assert_not_called()
        repo.count_featured_excluding.assert_not_called()
        activity.record.assert_not_called()
        _cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. VALIDATION — strict boolean
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidation:
    def setup_method(self):
        self.client = _client_with(lambda: MagicMock(spec=ToggleFeature))

    def teardown_method(self):
        _cleanup()

    def test_string_true_is_rejected_422(self):
        resp = self.client.patch(URL, json={"is_featured": "true"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert detail["message"] == "is_featured must be a boolean"

    def test_integer_one_is_rejected_422(self):
        resp = self.client.patch(URL, json={"is_featured": 1})
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "VALIDATION_ERROR"

    def test_null_is_rejected_422(self):
        resp = self.client.patch(URL, json={"is_featured": None})
        assert resp.status_code == 422

    def test_missing_field_is_rejected_422(self):
        resp = self.client.patch(URL, json={})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "required" in detail["message"]

    def test_real_boolean_true_passes_validation(self):
        from app.api.v1.schemas.project import ToggleFeatureRequest
        req = ToggleFeatureRequest(is_featured=True)
        assert req.is_featured is True

    def test_real_boolean_false_passes_validation(self):
        from app.api.v1.schemas.project import ToggleFeatureRequest
        req = ToggleFeatureRequest(is_featured=False)
        assert req.is_featured is False

    def test_string_false_rejected_at_schema_level(self):
        from app.api.v1.schemas.project import ToggleFeatureRequest
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            ToggleFeatureRequest.model_validate({"is_featured": "false"})


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NOT FOUND / PERMISSION / BAD UUID
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotFoundAndPermission:
    def teardown_method(self):
        _cleanup()

    def test_project_not_found_returns_404(self):
        uc = _make_real_use_case(project=None)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["error"] == "PROJECT_NOT_FOUND"
        assert detail["message"] == "Project not found"

    def test_not_found_checked_before_db_write(self):
        repo = MagicMock()
        repo.get_with_blocks.return_value = None
        uc = ToggleFeature(repo=repo, activity=MagicMock())
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 404
        repo.update.assert_not_called()
        _cleanup()

    def test_malformed_uuid_returns_422(self):
        client = _client_with(lambda: MagicMock(spec=ToggleFeature))
        resp = client.patch(
            "/api/v1/admin/projects/not-a-uuid/feature",
            json={"is_featured": True},
        )
        assert resp.status_code == 422

    def test_other_authors_project_returns_403(self):
        project = _fake_project(author_id=uuid.uuid4())
        uc = _make_real_use_case(project)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "FORBIDDEN"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FEATURED LIMIT (409)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeaturedLimit:
    def teardown_method(self):
        _cleanup()

    def test_exceeding_limit_returns_409(self):
        project = _fake_project(is_featured=False)
        # MAX others already featured → featuring this one would exceed the cap
        uc = _make_real_use_case(project, featured_others=MAX_FEATURED_PROJECTS)
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "FEATURED_LIMIT_REACHED"
        assert str(MAX_FEATURED_PROJECTS) in detail["message"]

    def test_at_limit_minus_one_is_allowed(self):
        project = _fake_project(is_featured=False)
        uc = _make_real_use_case(
            project, featured_others=MAX_FEATURED_PROJECTS - 1, updated_is_featured=True
        )
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 200

    def test_unfeature_never_hits_limit(self):
        """Turning OFF never checks the cap, even if many are featured."""
        project = _fake_project(is_featured=True)
        repo = MagicMock()
        repo.get_with_blocks.return_value = (project, [])
        updated = _fake_project(is_featured=False)
        repo.update.return_value = (updated, [])
        uc = ToggleFeature(repo=repo, activity=MagicMock())
        client = _client_with(lambda: uc)
        resp = client.patch(URL, json={"is_featured": False})
        assert resp.status_code == 200
        repo.count_featured_excluding.assert_not_called()
        _cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    def test_missing_token_returns_401(self):
        app.dependency_overrides.pop(get_current_admin, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(URL, json={"is_featured": True})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        app.dependency_overrides.pop(get_current_admin, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            URL,
            headers={"Authorization": "Bearer not.a.real.token"},
            json={"is_featured": True},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 7. USE-CASE UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestToggleFeatureUseCase:
    def _build(self, project=None, featured_others=0, updated_state=None):
        repo = MagicMock()
        activity = MagicMock()
        if project is None:
            repo.get_with_blocks.return_value = None
        else:
            repo.get_with_blocks.return_value = (project, [])
        repo.count_featured_excluding.return_value = featured_others
        if project is not None:
            state = updated_state if updated_state is not None else (not project.is_featured)
            repo.update.return_value = (_fake_project(is_featured=state), [])
        return ToggleFeature(repo=repo, activity=activity), repo, activity

    def _cmd(self, is_featured=True):
        return ToggleFeatureCommand(
            project_id=PROJECT_ID, requester_id=ADMIN_ID, is_featured=is_featured
        )

    def test_raises_not_found(self):
        uc, _, _ = self._build(project=None)
        with pytest.raises(NotFoundError):
            uc.execute(self._cmd(True))

    def test_raises_permission_error_for_wrong_author(self):
        project = _fake_project(author_id=uuid.uuid4())
        uc, _, _ = self._build(project=project)
        with pytest.raises(PermissionError):
            uc.execute(self._cmd(True))

    def test_raises_featured_limit_error(self):
        project = _fake_project(is_featured=False)
        uc, _, _ = self._build(project=project, featured_others=MAX_FEATURED_PROJECTS)
        with pytest.raises(FeaturedLimitError):
            uc.execute(self._cmd(True))

    def test_noop_returns_current_state_without_write(self):
        project = _fake_project(is_featured=True)
        uc, repo, activity = self._build(project=project)
        result = uc.execute(self._cmd(True))
        assert result.is_featured is True
        repo.update.assert_not_called()
        activity.record.assert_not_called()

    def test_feature_calls_update_with_true(self):
        project = _fake_project(is_featured=False)
        uc, repo, _ = self._build(project=project, updated_state=True)
        uc.execute(self._cmd(True))
        repo.update.assert_called_once_with(PROJECT_ID, {"is_featured": True})

    def test_unfeature_calls_update_with_false(self):
        project = _fake_project(is_featured=True)
        uc, repo, _ = self._build(project=project, updated_state=False)
        uc.execute(self._cmd(False))
        repo.update.assert_called_once_with(PROJECT_ID, {"is_featured": False})

    def test_activity_recorded_on_feature(self):
        project = _fake_project(is_featured=False)
        uc, _, activity = self._build(project=project, updated_state=True)
        uc.execute(self._cmd(True))
        activity.record.assert_called_once()
        kwargs = activity.record.call_args.kwargs
        assert kwargs["action_type"] == "project_updated"
        assert kwargs["entity_id"] == PROJECT_ID
        assert "featured" in kwargs["description"]

    def test_returns_toggle_feature_result(self):
        project = _fake_project(is_featured=False)
        uc, _, _ = self._build(project=project, updated_state=True)
        result = uc.execute(self._cmd(True))
        assert isinstance(result, ToggleFeatureResult)
        assert result.id == PROJECT_ID
        assert result.is_featured is True

    def test_limit_not_checked_when_unfeaturing(self):
        project = _fake_project(is_featured=True)
        uc, repo, _ = self._build(project=project, updated_state=False)
        uc.execute(self._cmd(False))
        repo.count_featured_excluding.assert_not_called()

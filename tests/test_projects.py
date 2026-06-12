"""End-to-end tests for API 9 — POST /api/v1/admin/projects/{id}/blocks.

Each test overrides FastAPI dependencies so no real database or Supabase
project is needed. The auth dependency is stubbed with a fake admin user;
the add_block use case is either:
  - a real AddBlock instance backed by mock repositories (business-rule tests)
  - a preconfigured MagicMock (HTTP-mapping tests)
"""
from __future__ import annotations

import datetime
import json
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

from app.application.dtos.project import BlockResult
from app.application.use_cases.projects.add_block import AddBlock
from app.domain.entities.block import Block
from app.domain.entities.project import Project
from app.domain.exceptions import (
    CodeTooLongError,
    NotFoundError,
    PermissionError,
    ValidationError,
)
from app.infrastructure.persistence.orm.models import UserRole, Users
from app.main import app
from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_add_block

# ── shared fixtures ───────────────────────────────────────────────────────────

ADMIN_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("c3d4e5f6-1111-1111-1111-000000000001")
BLOCK_ID = uuid.UUID("e5f6a7b8-2222-2222-2222-000000000003")
NOW = datetime.datetime(2026, 6, 12, 10, 10, 0, tzinfo=datetime.timezone.utc)
URL = f"/api/v1/admin/projects/{PROJECT_ID}/blocks"

STATS_CONFIG = {
    "metrics": [
        {"value": "99.9%", "label": "Uptime"},
        {"value": "12k", "label": "API calls/day"},
        {"value": "<50ms", "label": "Avg latency"},
    ],
    "columns": 3,
    "style": "card",
}

STATS_RESULT_CONFIG = {
    "metrics": [
        {"value": "99.9%", "label": "Uptime", "unit": None, "icon": None, "color": None},
        {"value": "12k", "label": "API calls/day", "unit": None, "icon": None, "color": None},
        {"value": "<50ms", "label": "Avg latency", "unit": None, "icon": None, "color": None},
    ],
    "columns": 3,
    "style": "card",
}


def _fake_admin():
    """Return a minimal Users mock that satisfies get_current_admin."""
    user = MagicMock(spec=Users)
    user.id = ADMIN_ID
    user.role = UserRole.ADMIN
    user.is_blocked = False
    return user


def _fake_block_result(**overrides) -> BlockResult:
    defaults = dict(
        id=BLOCK_ID,
        project_id=PROJECT_ID,
        block_type="stats",
        position=2,
        config=STATS_RESULT_CONFIG,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return BlockResult(**defaults)


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


def _fake_block(block_type: str = "stats", position: int = 0, config: dict | None = None) -> Block:
    return Block(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        block_type=block_type,
        position=position,
        config=config or {},
        created_at=NOW,
        updated_at=NOW,
    )


def _make_real_use_case(
    project: Project | None = None,
    existing_blocks: list[Block] | None = None,
    returned_block: Block | None = None,
    project_repo_raises=None,
) -> AddBlock:
    """Build a real AddBlock wired to mock repositories."""
    project_repo = MagicMock()
    block_repo = MagicMock()
    activity = MagicMock()

    if project_repo_raises is not None:
        project_repo.get_with_blocks.side_effect = project_repo_raises
    elif project is None:
        project_repo.get_with_blocks.return_value = None
    else:
        project_repo.get_with_blocks.return_value = (
            project,
            existing_blocks or [],
        )

    if returned_block is not None:
        block_repo.add.return_value = returned_block
    else:
        block_repo.add.return_value = _fake_block("stats", 2, STATS_RESULT_CONFIG)

    return AddBlock(project_repo=project_repo, block_repo=block_repo, activity=activity)


# ── helpers for dependency overrides ─────────────────────────────────────────


def _client_with(use_case_factory) -> TestClient:
    """Return a TestClient with auth stubbed and add_block set to the given factory."""
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_add_block] = use_case_factory
    client = TestClient(app, raise_server_exceptions=False)
    return client


def _cleanup():
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_add_block, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddBlockHappyPath:
    def setup_method(self):
        self.project = _fake_project()
        self.returned_block = _fake_block("stats", 2, STATS_RESULT_CONFIG)
        self.returned_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="stats",
            position=2, config=STATS_RESULT_CONFIG, created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(
            project=self.project,
            existing_blocks=[_fake_block("hero", 0), _fake_block("text", 1)],
            returned_block=self.returned_block,
        )
        self.client = _client_with(lambda: uc)

    def teardown_method(self):
        _cleanup()

    def test_returns_201(self):
        resp = self.client.post(URL, json={"block_type": "stats", "position": 2, "config": STATS_CONFIG})
        assert resp.status_code == 201

    def test_response_shape(self):
        resp = self.client.post(URL, json={"block_type": "stats", "position": 2, "config": STATS_CONFIG})
        body = resp.json()
        assert body["id"] == str(BLOCK_ID)
        assert body["project_id"] == str(PROJECT_ID)
        assert body["block_type"] == "stats"
        assert body["position"] == 2
        assert body["config"]["columns"] == 3
        assert body["config"]["style"] == "card"
        assert body["created_at"] == "2026-06-12T10:10:00Z"
        assert body["updated_at"] == "2026-06-12T10:10:00Z"

    def test_hero_block(self):
        hero_config = {
            "heading": "Jerry — Public AI Assistant",
            "subheading": "Ask me anything",
            "align": "center",
        }
        hero_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="hero",
            position=0, config=hero_config, created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(
            project=self.project,
            existing_blocks=[],
            returned_block=hero_block,
        )
        client = _client_with(lambda: uc)
        resp = client.post(URL, json={"block_type": "hero", "position": 0, "config": hero_config})
        assert resp.status_code == 201
        assert resp.json()["block_type"] == "hero"
        _cleanup()

    def test_empty_gallery_is_valid(self):
        gallery_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="gallery",
            position=0, config={"images": [], "layout": "grid", "columns": 3, "gap": "md", "show_captions": True},
            created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(
            project=self.project,
            existing_blocks=[],
            returned_block=gallery_block,
        )
        client = _client_with(lambda: uc)
        resp = client.post(URL, json={"block_type": "gallery", "position": 0, "config": {"images": []}})
        assert resp.status_code == 201
        _cleanup()

    def test_position_clamped_when_greater_than_block_count(self):
        """position=99 with 2 existing blocks → clamped to 2 (append)."""
        clamp_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="stats",
            position=2, config=STATS_RESULT_CONFIG, created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(
            project=self.project,
            existing_blocks=[_fake_block("hero", 0), _fake_block("text", 1)],
            returned_block=clamp_block,
        )
        client = _client_with(lambda: uc)
        resp = client.post(URL, json={"block_type": "stats", "position": 99, "config": STATS_CONFIG})
        assert resp.status_code == 201
        assert resp.json()["position"] == 2
        _cleanup()

    def test_position_zero_with_no_blocks(self):
        first_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="stats",
            position=0, config=STATS_RESULT_CONFIG, created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(
            project=self.project,
            existing_blocks=[],
            returned_block=first_block,
        )
        client = _client_with(lambda: uc)
        resp = client.post(URL, json={"block_type": "stats", "position": 0, "config": STATS_CONFIG})
        assert resp.status_code == 201
        assert resp.json()["position"] == 0
        _cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. BLOCK TYPE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockTypeValidation:
    def setup_method(self):
        # Use a mock use case — these tests never reach the use case
        mock_uc = MagicMock(spec=AddBlock)
        self.client = _client_with(lambda: mock_uc)

    def teardown_method(self):
        _cleanup()

    def test_unsupported_block_type_returns_422(self):
        resp = self.client.post(URL, json={"block_type": "banner", "position": 0, "config": {}})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "banner" in detail["message"]

    def test_metrics_alias_is_rejected(self):
        """'metrics' is not a valid type — only 'stats' is."""
        resp = self.client.post(
            URL,
            json={"block_type": "metrics", "position": 0, "config": {"metrics": [], "columns": 3, "style": "card"}},
        )
        assert resp.status_code == 422
        assert "metrics" in resp.json()["detail"]["message"]

    def test_empty_block_type_is_rejected(self):
        resp = self.client.post(URL, json={"block_type": "", "position": 0, "config": {}})
        assert resp.status_code == 422

    def test_all_13_types_are_accepted_at_schema_level(self):
        """Verify no type in the 13 is accidentally mapped to None."""
        from app.api.v1.schemas.block_config import BLOCK_CONFIG_MODELS
        assert len(BLOCK_CONFIG_MODELS) == 13
        for t in BLOCK_CONFIG_MODELS:
            assert BLOCK_CONFIG_MODELS[t] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CONFIG SCHEMA VALIDATION (Pydantic, checked in the endpoint before use case)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigSchemaValidation:
    def setup_method(self):
        mock_uc = MagicMock(spec=AddBlock)
        self.client = _client_with(lambda: mock_uc)

    def teardown_method(self):
        _cleanup()

    def test_hero_without_heading_returns_422(self):
        resp = self.client.post(
            URL,
            json={"block_type": "hero", "position": 0, "config": {"subheading": "only sub"}},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"

    def test_image_without_image_url_returns_422(self):
        resp = self.client.post(
            URL,
            json={"block_type": "image", "position": 0, "config": {"alt_text": "no url"}},
        )
        assert resp.status_code == 422

    def test_form_without_form_id_returns_422(self):
        resp = self.client.post(
            URL,
            json={"block_type": "form", "position": 0, "config": {"embed_type": "typeform"}},
        )
        assert resp.status_code == 422

    def test_extra_config_fields_are_ignored(self):
        """Unknown config fields must NOT cause a 422 — they're silently dropped."""
        from app.api.v1.schemas.block_config import TextConfig
        result = TextConfig.model_validate({"content": "hello", "unknown_field": "ignored"})
        assert result.content == "hello"
        assert not hasattr(result, "unknown_field")

    def test_config_too_large_returns_422(self):
        oversized = {"content": "x" * 70_000}
        resp = self.client.post(
            URL,
            json={"block_type": "text", "position": 0, "config": oversized},
        )
        assert resp.status_code == 422

    def test_video_block_requires_video_url(self):
        resp = self.client.post(
            URL,
            json={"block_type": "video", "position": 0, "config": {"provider": "cloudinary"}},
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BUSINESS-RULE VALIDATION (enforced in the use case)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBusinessRules:
    def setup_method(self):
        self.project = _fake_project()

    def teardown_method(self):
        _cleanup()

    def _client_for(self, uc: AddBlock) -> TestClient:
        return _client_with(lambda: uc)

    def test_poll_with_one_option_returns_422(self):
        uc = _make_real_use_case(project=self.project, existing_blocks=[])
        client = self._client_for(uc)
        resp = client.post(
            URL,
            json={
                "block_type": "poll",
                "position": 0,
                "config": {
                    "question": "Yes or no?",
                    "options": ["Yes"],  # only 1 — violates min 2
                },
            },
        )
        _cleanup()
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "2" in detail["message"]  # "at least 2 items"

    def test_poll_with_seven_options_returns_422(self):
        uc = _make_real_use_case(project=self.project, existing_blocks=[])
        client = self._client_for(uc)
        resp = client.post(
            URL,
            json={
                "block_type": "poll",
                "position": 0,
                "config": {
                    "question": "Pick one",
                    "options": ["A", "B", "C", "D", "E", "F", "G"],  # 7 — violates max 6
                },
            },
        )
        _cleanup()
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "6" in detail["message"]

    def test_poll_with_two_options_is_valid(self):
        poll_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="poll", position=0,
            config={"question": "Yes?", "options": ["Yes", "No"], "anonymous": True, "show_results": True, "expiry_date": None},
            created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(project=self.project, existing_blocks=[], returned_block=poll_block)
        client = self._client_for(uc)
        resp = client.post(
            URL,
            json={
                "block_type": "poll",
                "position": 0,
                "config": {"question": "Yes?", "options": ["Yes", "No"]},
            },
        )
        _cleanup()
        assert resp.status_code == 201

    def test_poll_with_six_options_is_valid(self):
        poll_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="poll", position=0,
            config={"question": "Pick", "options": ["A", "B", "C", "D", "E", "F"], "anonymous": True, "show_results": True, "expiry_date": None},
            created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(project=self.project, existing_blocks=[], returned_block=poll_block)
        client = self._client_for(uc)
        resp = client.post(
            URL,
            json={
                "block_type": "poll",
                "position": 0,
                "config": {"question": "Pick", "options": ["A", "B", "C", "D", "E", "F"]},
            },
        )
        _cleanup()
        assert resp.status_code == 201

    def test_code_block_exceeding_50k_chars_returns_422(self):
        uc = _make_real_use_case(project=self.project, existing_blocks=[])
        client = self._client_for(uc)
        # Must be under 64 KB (our new payload limit) but over 50k chars
        code_50001 = "x" * 50_001
        resp = client.post(
            URL,
            json={"block_type": "code", "position": 0, "config": {"code": code_50001, "language": "python"}},
        )
        _cleanup()
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "CODE_TOO_LONG"

    def test_code_block_at_50k_chars_is_valid(self):
        code_50000 = "x" * 50_000
        code_block = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="code", position=0,
            config={"code": code_50000, "language": "python", "filename": None,
                    "show_line_numbers": True, "highlight_lines": [], "theme": "dark"},
            created_at=NOW, updated_at=NOW,
        )
        uc = _make_real_use_case(project=self.project, existing_blocks=[], returned_block=code_block)
        client = self._client_for(uc)
        resp = client.post(
            URL,
            json={"block_type": "code", "position": 0, "config": {"code": code_50000}},
        )
        _cleanup()
        assert resp.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# 5. NOT-FOUND AND PERMISSION
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotFoundAndPermission:
    def teardown_method(self):
        _cleanup()

    def test_project_not_found_returns_404(self):
        uc = _make_real_use_case(project=None)  # get_with_blocks returns None
        client = _client_with(lambda: uc)
        resp = client.post(URL, json={"block_type": "stats", "position": 0, "config": STATS_CONFIG})
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["error"] == "PROJECT_NOT_FOUND"

    def test_malformed_project_uuid_returns_422(self):
        mock_uc = MagicMock(spec=AddBlock)
        client = _client_with(lambda: mock_uc)
        resp = client.post(
            "/api/v1/admin/projects/not-a-uuid/blocks",
            json={"block_type": "stats", "position": 0, "config": STATS_CONFIG},
        )
        assert resp.status_code == 422

    def test_project_belongs_to_different_author_returns_403(self):
        other_author_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
        project_other = _fake_project(author_id=other_author_id)
        uc = _make_real_use_case(project=project_other, existing_blocks=[])
        client = _client_with(lambda: uc)
        resp = client.post(URL, json={"block_type": "stats", "position": 0, "config": STATS_CONFIG})
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["error"] == "FORBIDDEN"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    def test_missing_bearer_token_returns_401(self):
        # Do NOT override get_current_admin — let the real auth run (no token → 401)
        app.dependency_overrides.pop(get_current_admin, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(URL, json={"block_type": "stats", "position": 0, "config": STATS_CONFIG})
        assert resp.status_code == 401

    def test_invalid_bearer_token_returns_401(self):
        app.dependency_overrides.pop(get_current_admin, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            URL,
            headers={"Authorization": "Bearer this.is.not.valid"},
            json={"block_type": "stats", "position": 0, "config": STATS_CONFIG},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 7. REQUEST BODY VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequestBodyValidation:
    def setup_method(self):
        mock_uc = MagicMock(spec=AddBlock)
        self.client = _client_with(lambda: mock_uc)

    def teardown_method(self):
        _cleanup()

    def test_missing_block_type_returns_422(self):
        resp = self.client.post(URL, json={"position": 0, "config": {}})
        assert resp.status_code == 422

    def test_missing_position_returns_422(self):
        resp = self.client.post(URL, json={"block_type": "stats", "config": {}})
        assert resp.status_code == 422

    def test_missing_config_returns_422(self):
        resp = self.client.post(URL, json={"block_type": "stats", "position": 0})
        assert resp.status_code == 422

    def test_negative_position_returns_422(self):
        resp = self.client.post(URL, json={"block_type": "stats", "position": -1, "config": STATS_CONFIG})
        assert resp.status_code == 422

    def test_position_zero_is_valid(self):
        """position=0 is the minimum allowed value."""
        from app.api.v1.schemas.project import AddBlockRequest
        req = AddBlockRequest(block_type="stats", position=0, config=STATS_CONFIG)
        assert req.position == 0

    def test_empty_body_returns_422(self):
        resp = self.client.post(URL, json={})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 8. UNIT TESTS — AddBlock use case in isolation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddBlockUseCase:
    """Pure unit tests — no HTTP, no TestClient."""

    def _build_uc(self, project=None, blocks=None, returned_block=None):
        project_repo = MagicMock()
        block_repo = MagicMock()
        activity = MagicMock()

        if project is None:
            project_repo.get_with_blocks.return_value = None
        else:
            project_repo.get_with_blocks.return_value = (project, blocks or [])

        if returned_block:
            block_repo.add.return_value = returned_block
        else:
            block_repo.add.return_value = Block(
                id=BLOCK_ID, project_id=PROJECT_ID, block_type="stats",
                position=0, config={}, created_at=NOW, updated_at=NOW,
            )

        return AddBlock(project_repo=project_repo, block_repo=block_repo, activity=activity), \
               project_repo, block_repo, activity

    def _cmd(self, **overrides):
        from app.application.dtos.project import AddBlockCommand
        defaults = dict(
            project_id=PROJECT_ID,
            requester_id=ADMIN_ID,
            block_type="stats",
            position=0,
            config={"metrics": [{"value": "1", "label": "x", "unit": None, "icon": None, "color": None}], "columns": 1, "style": "card"},
        )
        defaults.update(overrides)
        return AddBlockCommand(**defaults)

    def test_raises_not_found_when_project_missing(self):
        uc, _, _, _ = self._build_uc(project=None)
        with pytest.raises(NotFoundError):
            uc.execute(self._cmd())

    def test_raises_permission_error_for_wrong_author(self):
        project = _fake_project(author_id=uuid.uuid4())
        uc, _, _, _ = self._build_uc(project=project)
        with pytest.raises(PermissionError):
            uc.execute(self._cmd())

    def test_raises_validation_error_for_unsupported_block_type(self):
        project = _fake_project()
        uc, _, _, _ = self._build_uc(project=project)
        with pytest.raises(ValidationError, match="not supported"):
            uc.execute(self._cmd(block_type="banner"))

    def test_raises_validation_error_for_poll_with_one_option(self):
        project = _fake_project()
        uc, _, _, _ = self._build_uc(project=project)
        with pytest.raises(ValidationError, match="at least 2"):
            uc.execute(self._cmd(
                block_type="poll",
                config={"question": "?", "options": ["A"], "anonymous": True, "show_results": True, "expiry_date": None},
            ))

    def test_raises_validation_error_for_poll_with_seven_options(self):
        project = _fake_project()
        uc, _, _, _ = self._build_uc(project=project)
        with pytest.raises(ValidationError, match="more than 6"):
            uc.execute(self._cmd(
                block_type="poll",
                config={"question": "?", "options": list("ABCDEFG"), "anonymous": True, "show_results": True, "expiry_date": None},
            ))

    def test_raises_code_too_long_error(self):
        project = _fake_project()
        uc, _, _, _ = self._build_uc(project=project)
        with pytest.raises(CodeTooLongError):
            uc.execute(self._cmd(
                block_type="code",
                config={"code": "x" * 50_001, "language": "python", "filename": None,
                        "show_line_numbers": True, "highlight_lines": [], "theme": "dark"},
            ))

    def test_position_is_clamped_to_block_count(self):
        project = _fake_project()
        existing = [_fake_block("hero", 0), _fake_block("text", 1)]  # 2 blocks
        returned = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="stats",
            position=2, config={}, created_at=NOW, updated_at=NOW,
        )
        uc, _, block_repo, _ = self._build_uc(project=project, blocks=existing, returned_block=returned)
        result = uc.execute(self._cmd(position=99))
        # Check that block_repo.add was called with position=2 (clamped from 99)
        call_args = block_repo.add.call_args[0][0]
        assert call_args.position == 2

    def test_position_zero_is_not_clamped(self):
        project = _fake_project()
        existing = [_fake_block("hero", 0), _fake_block("text", 1)]
        uc, _, block_repo, _ = self._build_uc(project=project, blocks=existing)
        uc.execute(self._cmd(position=0))
        call_args = block_repo.add.call_args[0][0]
        assert call_args.position == 0

    def test_shift_is_called_before_add(self):
        project = _fake_project()
        existing = [_fake_block("hero", 0)]
        uc, _, block_repo, _ = self._build_uc(project=project, blocks=existing)
        uc.execute(self._cmd(position=0))
        block_repo.shift_positions_from.assert_called_once_with(PROJECT_ID, 0)
        block_repo.add.assert_called_once()

    def test_activity_is_recorded_on_success(self):
        project = _fake_project()
        uc, _, _, activity = self._build_uc(project=project)
        uc.execute(self._cmd())
        activity.record.assert_called_once()
        record_kwargs = activity.record.call_args.kwargs
        assert record_kwargs["action_type"] == "project_updated"
        assert record_kwargs["entity_id"] == PROJECT_ID

    def test_returns_block_result(self):
        project = _fake_project()
        returned = Block(
            id=BLOCK_ID, project_id=PROJECT_ID, block_type="stats",
            position=0, config={"metrics": [], "columns": 3, "style": "card"},
            created_at=NOW, updated_at=NOW,
        )
        uc, _, _, _ = self._build_uc(project=project, returned_block=returned)
        result = uc.execute(self._cmd())
        assert isinstance(result, BlockResult)
        assert result.id == BLOCK_ID
        assert result.block_type == "stats"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. UNIT TESTS — block_config schemas
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockConfigSchemas:
    def test_stats_rejects_block_type_metrics(self):
        """Verify the discriminated literal prevents 'metrics' from being accepted."""
        from app.api.v1.schemas.block_config import BLOCK_CONFIG_MODELS
        assert "metrics" not in BLOCK_CONFIG_MODELS
        assert "stats" in BLOCK_CONFIG_MODELS

    def test_hero_requires_heading(self):
        from app.api.v1.schemas.block_config import HeroConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            HeroConfig.model_validate({})

    def test_hero_minimal_valid(self):
        from app.api.v1.schemas.block_config import HeroConfig
        cfg = HeroConfig.model_validate({"heading": "Hello"})
        assert cfg.heading == "Hello"
        assert cfg.align == "center"

    def test_gallery_empty_images_is_valid(self):
        from app.api.v1.schemas.block_config import GalleryConfig
        cfg = GalleryConfig.model_validate({"images": []})
        assert cfg.images == []

    def test_poll_options_list_shape(self):
        from app.api.v1.schemas.block_config import PollConfig
        cfg = PollConfig.model_validate({"question": "Q?", "options": ["A", "B", "C"]})
        assert len(cfg.options) == 3

    def test_code_config_defaults(self):
        from app.api.v1.schemas.block_config import CodeConfig
        cfg = CodeConfig.model_validate({"code": "print('hi')"})
        assert cfg.language == "plaintext"
        assert cfg.show_line_numbers is True
        assert cfg.theme == "dark"

    def test_comparison_all_fields_required(self):
        from app.api.v1.schemas.block_config import ComparisonConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            ComparisonConfig.model_validate({"left_label": "A"})  # missing 3 fields

    def test_cta_requires_heading(self):
        from app.api.v1.schemas.block_config import CtaConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            CtaConfig.model_validate({"primary_label": "Go"})

    def test_form_requires_form_id(self):
        from app.api.v1.schemas.block_config import FormConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            FormConfig.model_validate({"embed_type": "typeform"})

    def test_video_requires_video_url(self):
        from app.api.v1.schemas.block_config import VideoConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            VideoConfig.model_validate({"provider": "cloudinary"})

    def test_text_requires_content(self):
        from app.api.v1.schemas.block_config import TextConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            TextConfig.model_validate({})

    def test_image_requires_image_url(self):
        from app.api.v1.schemas.block_config import ImageConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            ImageConfig.model_validate({})

    def test_quote_requires_text(self):
        from app.api.v1.schemas.block_config import QuoteConfig
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            QuoteConfig.model_validate({})

"""End-to-end tests for API 10 — PUT /api/v1/admin/projects/{id}/blocks/{block_id}.

Dependencies are overridden so no real DB or Supabase project is needed.
The auth dependency is stubbed with a fake admin; the UpdateBlock use case is
either a real instance wired to mock repositories + the real Pydantic config
validator (logic tests), or a MagicMock (HTTP-mapping tests).
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

from app.application.dtos.project import BlockResult, UpdateBlockCommand
from app.application.use_cases.projects.update_block import UpdateBlock
from app.api.v1.schemas.block_config import PydanticBlockConfigValidator
from app.domain.entities.block import Block
from app.domain.exceptions import CodeTooLongError, NotFoundError, ValidationError
from app.infrastructure.persistence.orm.models import UserRole, Users
from app.main import app
from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_update_block

# ── shared fixtures ───────────────────────────────────────────────────────────

ADMIN_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("c3d4e5f6-1111-1111-1111-000000000001")
BLOCK_ID = uuid.UUID("e5f6a7b8-2222-2222-2222-000000000003")
CREATED = datetime.datetime(2026, 6, 12, 10, 10, 0, tzinfo=datetime.timezone.utc)
UPDATED = datetime.datetime(2026, 6, 12, 10, 15, 0, tzinfo=datetime.timezone.utc)
URL = f"/api/v1/admin/projects/{PROJECT_ID}/blocks/{BLOCK_ID}"

# A stored stats config as it would look after AddBlock's model_dump (normalized).
STORED_STATS_CONFIG = {
    "metrics": [
        {"value": "99.9%", "label": "Uptime", "unit": None, "icon": None, "color": None},
        {"value": "12k", "label": "API calls/day", "unit": None, "icon": None, "color": None},
        {"value": "<50ms", "label": "Avg latency", "unit": None, "icon": None, "color": None},
    ],
    "columns": 3,
    "style": "card",
}


def _fake_admin():
    user = MagicMock(spec=Users)
    user.id = ADMIN_ID
    user.role = UserRole.ADMIN
    user.is_blocked = False
    return user


def _stored_block(block_type="stats", position=2, config=None) -> Block:
    return Block(
        id=BLOCK_ID,
        project_id=PROJECT_ID,
        block_type=block_type,
        position=position,
        config=config if config is not None else dict(STORED_STATS_CONFIG),
        created_at=CREATED,
        updated_at=CREATED,
    )


def _make_real_use_case(stored: Block | None):
    """Real UpdateBlock with the real Pydantic validator + mock block repo.

    block_repo.update_block echoes back a block reflecting the requested change
    (with updated_at bumped), mimicking the DB.
    """
    block_repo = MagicMock()
    activity = MagicMock()
    block_repo.get_for_project.return_value = stored

    def _fake_update(block_id, *, config=None, position=None):
        return Block(
            id=stored.id,
            project_id=stored.project_id,
            block_type=stored.block_type,
            position=position if position is not None else stored.position,
            config=config if config is not None else stored.config,
            created_at=stored.created_at,
            updated_at=UPDATED,
        )

    block_repo.update_block.side_effect = _fake_update
    uc = UpdateBlock(
        block_repo=block_repo,
        config_validator=PydanticBlockConfigValidator(),
        activity=activity,
    )
    return uc, block_repo, activity


def _client_with(use_case_factory) -> TestClient:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_update_block] = use_case_factory
    return TestClient(app, raise_server_exceptions=False)


def _cleanup():
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_update_block, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════════════

class TestHappyPath:
    def teardown_method(self):
        _cleanup()

    def test_update_position_and_config_returns_200(self):
        stored = _stored_block()
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(
            URL,
            json={
                "position": 3,
                "config": {
                    "metrics": [
                        {"value": "99.9%", "label": "Uptime"},
                        {"value": "15k", "label": "API calls/day"},
                    ],
                    "columns": 2,
                    "style": "minimal",
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(BLOCK_ID)
        assert body["project_id"] == str(PROJECT_ID)
        assert body["block_type"] == "stats"
        assert body["position"] == 3
        assert body["config"]["columns"] == 2
        assert body["config"]["style"] == "minimal"
        assert len(body["config"]["metrics"]) == 2
        assert body["created_at"] == "2026-06-12T10:10:00Z"
        assert body["updated_at"] == "2026-06-12T10:15:00Z"

    def test_update_position_only(self):
        stored = _stored_block()
        uc, repo, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"position": 5})
        assert resp.status_code == 200
        assert resp.json()["position"] == 5
        # config untouched
        assert repo.update_block.call_args.kwargs["config"] is None

    def test_block_type_stays_stats_in_response(self):
        stored = _stored_block()
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"columns": 4}})
        assert resp.status_code == 200
        assert resp.json()["block_type"] == "stats"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PARTIAL CONFIG MERGE
# ═══════════════════════════════════════════════════════════════════════════════

class TestPartialMerge:
    def teardown_method(self):
        _cleanup()

    def test_partial_config_does_not_wipe_other_keys(self):
        """Sending only {columns:2} must preserve the metrics array."""
        stored = _stored_block()
        uc, repo, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"columns": 2}})
        assert resp.status_code == 200
        body = resp.json()
        assert body["config"]["columns"] == 2
        # metrics preserved from stored config
        assert len(body["config"]["metrics"]) == 3
        assert body["config"]["style"] == "card"

    def test_merge_overrides_only_provided_keys(self):
        stored = _stored_block()
        uc, repo, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        client.put(URL, json={"config": {"style": "minimal"}})
        persisted = repo.update_block.call_args.kwargs["config"]
        assert persisted["style"] == "minimal"
        assert persisted["columns"] == 3  # unchanged
        assert len(persisted["metrics"]) == 3  # unchanged


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NO-OP CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoOp:
    def teardown_method(self):
        _cleanup()

    def test_empty_config_is_200_noop(self):
        stored = _stored_block()
        uc, repo, activity = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {}})
        assert resp.status_code == 200
        # no write, no activity — nothing actually changed
        repo.update_block.assert_not_called()
        activity.record.assert_not_called()
        # config returned unchanged
        assert resp.json()["config"]["columns"] == 3

    def test_empty_body_is_200_noop(self):
        stored = _stored_block()
        uc, repo, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={})
        assert resp.status_code == 200
        repo.update_block.assert_not_called()

    def test_setting_same_position_is_noop(self):
        stored = _stored_block(position=2)
        uc, repo, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"position": 2})
        assert resp.status_code == 200
        repo.update_block.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. block_type IS IMMUTABLE / IGNORED
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockTypeImmutable:
    def teardown_method(self):
        _cleanup()

    def test_block_type_in_body_is_silently_ignored(self):
        stored = _stored_block()
        uc, repo, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"block_type": "hero", "position": 4})
        assert resp.status_code == 200
        # block_type unchanged, no 422
        assert resp.json()["block_type"] == "stats"

    def test_block_type_change_attempt_does_not_revalidate_as_new_type(self):
        """Even with a hero-shaped config + block_type:hero, it stays a stats
        block and the config is validated against stats."""
        stored = _stored_block()
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        # columns must be an int for stats; this still validates as stats
        resp = client.put(URL, json={"block_type": "hero", "config": {"columns": 4}})
        assert resp.status_code == 200
        assert resp.json()["block_type"] == "stats"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CONFIG VALIDATION AFTER MERGE (422)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigValidation:
    def teardown_method(self):
        _cleanup()

    def test_invalid_merged_config_returns_422(self):
        """columns out of range (le=6) → invalid stats config after merge."""
        stored = _stored_block()
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"columns": 99}})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "VALIDATION_ERROR"
        assert "stats" in detail["message"]

    def test_invalid_metrics_type_returns_422(self):
        stored = _stored_block()
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"metrics": "not-a-list"}})
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "VALIDATION_ERROR"

    def test_poll_over_six_options_returns_422(self):
        stored = _stored_block(
            block_type="poll",
            config={
                "question": "Pick",
                "options": ["A", "B"],
                "anonymous": True,
                "show_results": True,
                "expiry_date": None,
            },
        )
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"options": list("ABCDEFG")}})
        assert resp.status_code == 422
        assert "6" in resp.json()["detail"]["message"]

    def test_poll_under_two_options_returns_422(self):
        stored = _stored_block(
            block_type="poll",
            config={
                "question": "Pick",
                "options": ["A", "B", "C"],
                "anonymous": True,
                "show_results": True,
                "expiry_date": None,
            },
        )
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"options": ["only-one"]}})
        assert resp.status_code == 422
        assert "2" in resp.json()["detail"]["message"]

    def test_code_over_limit_returns_422_code_too_long(self):
        stored = _stored_block(
            block_type="code",
            config={
                "code": "print('hi')",
                "language": "python",
                "filename": None,
                "show_line_numbers": True,
                "highlight_lines": [],
                "theme": "dark",
            },
        )
        uc, _, _ = _make_real_use_case(stored)
        client = _client_with(lambda: uc)
        # 50_001 chars but under the 64 KB request guard
        resp = client.put(URL, json={"config": {"code": "x" * 50_001}})
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "CODE_TOO_LONG"

    def test_oversized_config_request_returns_422(self):
        client = _client_with(lambda: MagicMock(spec=UpdateBlock))
        resp = client.put(URL, json={"config": {"code": "x" * 70_000}})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 6. NOT FOUND (404, never 403)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotFound:
    def teardown_method(self):
        _cleanup()

    def test_block_not_found_returns_404(self):
        uc, _, _ = _make_real_use_case(stored=None)
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"position": 1})
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["error"] == "BLOCK_NOT_FOUND"
        assert detail["message"] == "Block not found on this project"

    def test_block_on_different_project_returns_404_not_403(self):
        """get_for_project scopes by (block_id, project_id); a mismatch yields
        None → 404, never 403, never leaking the block exists elsewhere."""
        block_repo = MagicMock()
        block_repo.get_for_project.return_value = None  # wrong project → None
        uc = UpdateBlock(
            block_repo=block_repo,
            config_validator=PydanticBlockConfigValidator(),
            activity=MagicMock(),
        )
        client = _client_with(lambda: uc)
        resp = client.put(URL, json={"config": {"columns": 2}})
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "BLOCK_NOT_FOUND"
        # verify it was scoped by both ids
        block_repo.get_for_project.assert_called_once_with(BLOCK_ID, PROJECT_ID)

    def test_malformed_block_uuid_returns_422(self):
        client = _client_with(lambda: MagicMock(spec=UpdateBlock))
        resp = client.put(
            f"/api/v1/admin/projects/{PROJECT_ID}/blocks/not-a-uuid",
            json={"position": 1},
        )
        assert resp.status_code == 422

    def test_malformed_project_uuid_returns_422(self):
        client = _client_with(lambda: MagicMock(spec=UpdateBlock))
        resp = client.put(
            f"/api/v1/admin/projects/not-a-uuid/blocks/{BLOCK_ID}",
            json={"position": 1},
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 7. REQUEST BODY VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequestBodyValidation:
    def setup_method(self):
        self.client = _client_with(lambda: MagicMock(spec=UpdateBlock))

    def teardown_method(self):
        _cleanup()

    def test_negative_position_returns_422(self):
        resp = self.client.put(URL, json={"position": -1})
        assert resp.status_code == 422

    def test_position_zero_is_valid(self):
        from app.api.v1.schemas.project import UpdateBlockRequest
        req = UpdateBlockRequest(position=0)
        assert req.position == 0

    def test_config_null_is_accepted(self):
        from app.api.v1.schemas.project import UpdateBlockRequest
        req = UpdateBlockRequest.model_validate({"config": None})
        assert req.config is None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    def test_missing_token_returns_401(self):
        app.dependency_overrides.pop(get_current_admin, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put(URL, json={"position": 1})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        app.dependency_overrides.pop(get_current_admin, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put(
            URL,
            headers={"Authorization": "Bearer not.a.real.token"},
            json={"position": 1},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 9. USE-CASE UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateBlockUseCase:
    def _cmd(self, **overrides):
        defaults = dict(
            project_id=PROJECT_ID,
            block_id=BLOCK_ID,
            requester_id=ADMIN_ID,
            position=None,
            config=None,
        )
        defaults.update(overrides)
        return UpdateBlockCommand(**defaults)

    def test_raises_not_found_when_block_missing(self):
        uc, _, _ = _make_real_use_case(stored=None)
        with pytest.raises(NotFoundError):
            uc.execute(self._cmd(position=1))

    def test_merge_passed_to_repo(self):
        stored = _stored_block()
        uc, repo, _ = _make_real_use_case(stored)
        uc.execute(self._cmd(config={"columns": 2}))
        persisted = repo.update_block.call_args.kwargs["config"]
        assert persisted["columns"] == 2
        assert len(persisted["metrics"]) == 3

    def test_noop_returns_without_write(self):
        stored = _stored_block()
        uc, repo, activity = _make_real_use_case(stored)
        result = uc.execute(self._cmd(config={}))
        assert isinstance(result, BlockResult)
        repo.update_block.assert_not_called()
        activity.record.assert_not_called()

    def test_invalid_config_raises_validation_error(self):
        stored = _stored_block()
        uc, _, _ = _make_real_use_case(stored)
        with pytest.raises(ValidationError):
            uc.execute(self._cmd(config={"columns": 99}))

    def test_code_too_long_raises(self):
        stored = _stored_block(
            block_type="code",
            config={
                "code": "x", "language": "python", "filename": None,
                "show_line_numbers": True, "highlight_lines": [], "theme": "dark",
            },
        )
        uc, _, _ = _make_real_use_case(stored)
        with pytest.raises(CodeTooLongError):
            uc.execute(self._cmd(config={"code": "x" * 50_001}))

    def test_activity_recorded_on_real_change(self):
        stored = _stored_block()
        uc, _, activity = _make_real_use_case(stored)
        uc.execute(self._cmd(position=9))
        activity.record.assert_called_once()
        kwargs = activity.record.call_args.kwargs
        assert kwargs["action_type"] == "project_updated"
        assert kwargs["entity_id"] == PROJECT_ID

    def test_position_set_directly_no_shift(self):
        stored = _stored_block(position=2)
        uc, repo, _ = _make_real_use_case(stored)
        uc.execute(self._cmd(position=7))
        assert repo.update_block.call_args.kwargs["position"] == 7
        # update_block is the only repo write — no shift_positions_from call
        repo.shift_positions_from.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 10. CONFIG VALIDATOR UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPydanticBlockConfigValidator:
    def setup_method(self):
        self.v = PydanticBlockConfigValidator()

    def test_valid_stats_config_normalizes(self):
        out = self.v.validate("stats", {"metrics": [{"value": "1", "label": "x"}], "columns": 3, "style": "card"})
        assert out["metrics"][0]["unit"] is None  # default applied
        assert out["columns"] == 3

    def test_invalid_config_raises_validation_error(self):
        with pytest.raises(ValidationError, match="stats"):
            self.v.validate("stats", {"metrics": "nope"})

    def test_unknown_block_type_raises(self):
        with pytest.raises(ValidationError, match="not supported"):
            self.v.validate("banner", {})

    def test_returns_plain_dict(self):
        out = self.v.validate("text", {"content": "hello"})
        assert isinstance(out, dict)
        assert out["content"] == "hello"
        assert out["max_width"] == "default"

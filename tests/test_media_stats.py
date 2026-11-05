"""Tests for API 17 — GET /admin/media/stats.

Covers: use-case logic (humanize_bytes, percent calculation, last_cleanup wiring),
all spec edge cases (empty DB, zero quota, division guard), and the HTTP layer
(route ordering, auth guard, response shape).
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.application.dtos.media import CleanupStatsView, MediaStatsResult, StorageStatsView
from app.application.use_cases.media.get_media_stats import GetMediaStats, humanize_bytes
from app.domain.repositories.media_asset_repository import MediaStatsSnapshot


# ── helpers ───────────────────────────────────────────────────────────────────

def _snapshot(
    *,
    total_assets: int = 84,
    added_today: int = 4,
    counts: dict | None = None,
    used_bytes: int = 1_503_238_553,
    orphan_count: int = 0,
) -> MediaStatsSnapshot:
    return MediaStatsSnapshot(
        total_assets=total_assets,
        added_today=added_today,
        counts=counts if counts is not None else {"image": 71, "video": 9, "raw": 4},
        used_bytes=used_bytes,
        orphan_count=orphan_count,
    )


def _repo(snapshot: MediaStatsSnapshot | None = None) -> Mock:
    repo = Mock()
    repo.stats.return_value = snapshot or _snapshot()
    return repo


def _use_case(
    repo: Mock | None = None,
    *,
    quota_bytes: int = 2_415_919_104,
    plan: str = "PLUS",
) -> GetMediaStats:
    return GetMediaStats(repo=repo or _repo(), quota_bytes=quota_bytes, plan=plan)


# ── humanize_bytes ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("num, expected", [
    (0, "0 B"),
    (-1, "0 B"),
    (1023, "1023 B"),
    (1024, "1 KB"),
    (1_536, "1.5 KB"),
    (1_048_576, "1 MB"),
    (192_937_984, "184 MB"),
    (1_503_238_553, "1.4 GB"),
    (2_415_919_104, "2.25 GB"),
    (1_073_741_824, "1 GB"),
])
def test_humanize_bytes(num: int, expected: str) -> None:
    assert humanize_bytes(num) == expected


# ── use-case: happy path ──────────────────────────────────────────────────────

def test_execute_returns_correct_totals() -> None:
    snap = _snapshot(total_assets=84, added_today=4)
    result = _use_case(_repo(snap)).execute()

    assert result.total_assets == 84
    assert result.added_today == 4


def test_execute_returns_correct_type_counts() -> None:
    snap = _snapshot(counts={"image": 71, "video": 9, "raw": 4})
    result = _use_case(_repo(snap)).execute()

    assert result.counts == {"image": 71, "video": 9, "raw": 4}


def test_execute_returns_correct_storage_fields() -> None:
    snap = _snapshot(used_bytes=1_503_238_553)
    result = _use_case(_repo(snap), quota_bytes=2_415_919_104, plan="PLUS").execute()

    s = result.storage
    assert s.used_bytes == 1_503_238_553
    assert s.quota_bytes == 2_415_919_104
    assert s.used_human == "1.4 GB"
    assert s.quota_human == "2.25 GB"
    assert s.percent_used == 62
    assert s.plan == "PLUS"


def test_execute_percent_rounds_to_nearest_integer() -> None:
    # 1 / 3 = 33.333... → rounds to 33
    snap = _snapshot(used_bytes=1)
    result = _use_case(_repo(snap), quota_bytes=3).execute()
    assert result.storage.percent_used == 33


def test_execute_last_cleanup_is_none_by_default() -> None:
    result = _use_case().execute()
    assert result.last_cleanup is None


# ── edge case 1: empty DB ─────────────────────────────────────────────────────

def test_empty_db_returns_zero_counts() -> None:
    snap = _snapshot(total_assets=0, added_today=0, counts={"image": 0, "video": 0, "raw": 0}, used_bytes=0)
    result = _use_case(_repo(snap)).execute()

    assert result.total_assets == 0
    assert result.added_today == 0
    assert result.storage.used_bytes == 0
    assert result.storage.used_human == "0 B"
    assert result.storage.percent_used == 0


# ── edge case 2: quota is zero → guard against division by zero ───────────────

def test_zero_quota_returns_zero_percent_not_error() -> None:
    snap = _snapshot(used_bytes=500)
    result = _use_case(_repo(snap), quota_bytes=0).execute()
    assert result.storage.percent_used == 0


# ── edge case 3: used_bytes equals quota (100%) ───────────────────────────────

def test_percent_used_is_100_when_storage_full() -> None:
    quota = 2_415_919_104
    snap = _snapshot(used_bytes=quota)
    result = _use_case(_repo(snap), quota_bytes=quota).execute()
    assert result.storage.percent_used == 100


# ── edge case 4: used_bytes exceeds quota (over-limit) ───────────────────────

def test_percent_used_can_exceed_100() -> None:
    quota = 1_000
    snap = _snapshot(used_bytes=1_500)
    result = _use_case(_repo(snap), quota_bytes=quota).execute()
    assert result.storage.percent_used == 150


# ── edge case 5: plan label is passed through ─────────────────────────────────

def test_plan_label_is_forwarded_to_result() -> None:
    result = _use_case(plan="FREE").execute()
    assert result.storage.plan == "FREE"


# ── edge case 6: counts with all-zero resource types ─────────────────────────

def test_all_zero_counts_are_preserved() -> None:
    snap = _snapshot(counts={"image": 0, "video": 0, "raw": 0})
    result = _use_case(_repo(snap)).execute()
    assert result.counts == {"image": 0, "video": 0, "raw": 0}


# ── HTTP layer: route ordering (stats must beat /{asset_id}) ─────────────────

def test_stats_route_is_reachable_without_uuid_error() -> None:
    """FastAPI must resolve /stats BEFORE /{asset_id}. If the routes were
    reversed, 'stats' would be parsed as a UUID → 422. This test ensures
    the router is wired correctly."""
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_stats

    mock_uc = Mock()
    mock_uc.execute.return_value = MediaStatsResult(
        total_assets=0,
        added_today=0,
        counts={"image": 0, "video": 0, "raw": 0},
        storage=StorageStatsView(
            used_bytes=0,
            quota_bytes=2_415_919_104,
            used_human="0 B",
            quota_human="2.25 GB",
            percent_used=0,
            plan="PLUS",
        ),
        last_cleanup=None,
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_stats] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        # A 422 here means FastAPI tried to parse "stats" as a UUID.
        resp = client.get("/api/v1/admin/media/stats")
        assert resp.status_code != 422, (
            "Got 422 — 'stats' was interpreted as a UUID. "
            "Register /stats BEFORE /{asset_id} in the router."
        )
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_stats, None)


# ── HTTP layer: auth guard ────────────────────────────────────────────────────

def test_stats_requires_auth_token() -> None:
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/admin/media/stats")
    assert resp.status_code == 401


# ── HTTP layer: response shape ────────────────────────────────────────────────

def test_stats_response_shape_matches_spec() -> None:
    """Verify the JSON shape returned by the endpoint matches the API 17 spec."""
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_stats

    mock_uc = Mock()
    mock_uc.execute.return_value = MediaStatsResult(
        total_assets=84,
        added_today=4,
        counts={"image": 71, "video": 9, "raw": 4},
        storage=StorageStatsView(
            used_bytes=1_503_238_553,
            quota_bytes=2_415_919_104,
            used_human="1.4 GB",
            quota_human="2.25 GB",
            percent_used=62,
            plan="PLUS",
        ),
        last_cleanup=None,
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_stats] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/media/stats")
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_stats, None)

    assert resp.status_code == 200
    body = resp.json()

    assert body["total_assets"] == 84
    assert body["added_today"] == 4
    assert body["counts"] == {"image": 71, "video": 9, "raw": 4}

    storage = body["storage"]
    assert storage["used_bytes"] == 1_503_238_553
    assert storage["quota_bytes"] == 2_415_919_104
    assert storage["used_human"] == "1.4 GB"
    assert storage["quota_human"] == "2.25 GB"
    assert storage["percent_used"] == 62
    assert storage["plan"] == "PLUS"

    assert body["last_cleanup"] is None


def test_stats_response_includes_last_cleanup_when_present() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_stats

    ran_at = datetime.datetime(2026, 5, 30, 2, 0, 0, tzinfo=datetime.timezone.utc)
    mock_uc = Mock()
    mock_uc.execute.return_value = MediaStatsResult(
        total_assets=10,
        added_today=0,
        counts={"image": 10, "video": 0, "raw": 0},
        storage=StorageStatsView(
            used_bytes=0,
            quota_bytes=2_415_919_104,
            used_human="0 B",
            quota_human="2.25 GB",
            percent_used=0,
            plan="PLUS",
        ),
        last_cleanup=CleanupStatsView(
            ran_at=ran_at,
            freed_bytes=192_937_984,
            freed_human="184 MB",
            orphans_removed=3,
        ),
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_stats] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/media/stats")
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_stats, None)

    assert resp.status_code == 200
    cleanup = resp.json()["last_cleanup"]
    assert cleanup is not None
    assert cleanup["ran_at"] == "2026-05-30T02:00:00Z"
    assert cleanup["freed_bytes"] == 192_937_984
    assert cleanup["freed_human"] == "184 MB"
    assert cleanup["orphans_removed"] == 3

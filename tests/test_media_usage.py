"""Tests for API 18 — GET /admin/media/{id}/usage.

Covers:
  Use-case unit tests:
    - Happy path: asset not referenced (usage_count=0, references=[])
    - Happy path: asset referenced in project thumbnail
    - Happy path: asset referenced in project block
    - Happy path: asset referenced in blog cover / og / content
    - Happy path: multiple references across different sources
    - 404 when asset not found
    - YouTube asset (no public_id) → zero references, no DB scan
    - usage_count always equals len(references) (no separate COUNT query)
    - Admin URL routing: projects → /admin/projects/…, blogs/og → /admin/blogs/…

  HTTP layer tests:
    - 401 without auth token
    - 422 with a non-UUID path parameter
    - 404 when use case raises NotFoundError
    - 200 + empty references (safe-to-delete shape)
    - 200 + references (in-use shape, every field present)
    - Response shape matches spec (asset_id, usage_count, references[].kind/id/title/location/url)
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.application.dtos.media import MediaUsageResult, UsageReferenceView
from app.application.use_cases.media.get_media_usage import GetMediaUsage
from app.domain.entities.media_asset import MediaAsset
from app.domain.exceptions import NotFoundError
from app.domain.repositories.media_asset_repository import (
    MediaAssetListItem,
    MediaUsageRef,
)


# ── shared helpers ────────────────────────────────────────────────────────────

_NOW = datetime.datetime(2026, 6, 13, 12, 0, 0, tzinfo=datetime.timezone.utc)

ASSET_ID = uuid.UUID("f6a7b8c9-3333-3333-3333-000000000001")
PROJECT_ID = uuid.UUID("c3d4e5f6-1111-1111-1111-000000000001")
BLOG_ID = uuid.UUID("d7e8f9a0-2222-2222-2222-000000000001")
PUBLIC_ID = "projects/thumbnails/jerry-thumb"


def _asset(**overrides) -> MediaAsset:
    defaults = {
        "id": ASSET_ID,
        "cloudinary_url": f"https://res.cloudinary.com/demo/image/upload/v1/{PUBLIC_ID}.jpg",
        "public_id": PUBLIC_ID,
        "resource_type": "image",
        "format": "jpg",
        "width": 1200,
        "height": 630,
        "file_size": 214732,
        "file_name": "jerry-thumb.jpg",
        "folder": "projects/thumbnails",
        "alt_text": "Jerry thumbnail",
        "source_type": "cloudinary",
        "external_id": None,
        "thumbnail_url": None,
        "video_title": None,
        "video_duration_seconds": None,
        "file_hash": "abc123",
        "is_orphan": False,
        "uploaded_by": uuid.uuid4(),
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return MediaAsset(**defaults)


def _item(asset: MediaAsset | None = None) -> MediaAssetListItem:
    return MediaAssetListItem(asset=asset or _asset(), uploaded_by_name="Admin")


def _repo_with(
    asset: MediaAssetListItem | None = None,
    refs: list[MediaUsageRef] | None = None,
    not_found: bool = False,
) -> Mock:
    repo = Mock()
    repo.get.return_value = None if not_found else (asset or _item())
    repo.find_usage.return_value = refs or []
    return repo


def _use_case(repo: Mock) -> GetMediaUsage:
    return GetMediaUsage(repo=repo)


# ── use-case: not found ───────────────────────────────────────────────────────

def test_raises_not_found_for_unknown_id() -> None:
    repo = _repo_with(not_found=True)
    with pytest.raises(NotFoundError):
        _use_case(repo).execute(ASSET_ID)
    repo.get.assert_called_once_with(ASSET_ID)
    repo.find_usage.assert_not_called()


# ── use-case: zero references (safe to delete) ───────────────────────────────

def test_zero_references_when_asset_not_in_use() -> None:
    repo = _repo_with(refs=[])
    result = _use_case(repo).execute(ASSET_ID)

    assert result.asset_id == ASSET_ID
    assert result.usage_count == 0
    assert result.references == []
    repo.find_usage.assert_called_once_with(PUBLIC_ID)


# ── use-case: project thumbnail reference ────────────────────────────────────

def test_project_thumbnail_reference_is_returned() -> None:
    ref = MediaUsageRef(
        kind="project",
        entity_id=PROJECT_ID,
        title="Jerry — Public AI Assistant",
        location="thumbnail",
    )
    repo = _repo_with(refs=[ref])
    result = _use_case(repo).execute(ASSET_ID)

    assert result.usage_count == 1
    r = result.references[0]
    assert r.kind == "project"
    assert r.id == str(PROJECT_ID)
    assert r.title == "Jerry — Public AI Assistant"
    assert r.location == "thumbnail"
    assert r.url == f"/admin/projects/{PROJECT_ID}"


# ── use-case: project block reference ────────────────────────────────────────

def test_project_block_reference_is_returned() -> None:
    ref = MediaUsageRef(
        kind="project",
        entity_id=PROJECT_ID,
        title="Jerry — Public AI Assistant",
        location="image block",
    )
    repo = _repo_with(refs=[ref])
    result = _use_case(repo).execute(ASSET_ID)

    assert result.usage_count == 1
    r = result.references[0]
    assert r.kind == "project"
    assert r.location == "image block"
    assert r.url == f"/admin/projects/{PROJECT_ID}"


# ── use-case: blog cover reference ───────────────────────────────────────────

def test_blog_cover_reference_routes_to_admin_blogs() -> None:
    ref = MediaUsageRef(
        kind="blog",
        entity_id=BLOG_ID,
        title="My First Post",
        location="cover",
    )
    repo = _repo_with(refs=[ref])
    result = _use_case(repo).execute(ASSET_ID)

    assert result.usage_count == 1
    r = result.references[0]
    assert r.kind == "blog"
    assert r.location == "cover"
    assert r.url == f"/admin/blogs/{BLOG_ID}"


# ── use-case: og-image reference ─────────────────────────────────────────────

def test_og_image_reference_routes_to_admin_blogs() -> None:
    ref = MediaUsageRef(
        kind="og",
        entity_id=BLOG_ID,
        title="My First Post",
        location="og:image",
    )
    repo = _repo_with(refs=[ref])
    result = _use_case(repo).execute(ASSET_ID)

    r = result.references[0]
    assert r.kind == "og"
    assert r.location == "og:image"
    assert r.url == f"/admin/blogs/{BLOG_ID}"


# ── use-case: multiple references (mixed kinds) ───────────────────────────────

def test_multiple_references_all_returned() -> None:
    refs = [
        MediaUsageRef(kind="project", entity_id=PROJECT_ID, title="Project A", location="thumbnail"),
        MediaUsageRef(kind="project", entity_id=PROJECT_ID, title="Project A", location="image block"),
        MediaUsageRef(kind="blog", entity_id=BLOG_ID, title="Blog B", location="cover"),
        MediaUsageRef(kind="og", entity_id=BLOG_ID, title="Blog B", location="og:image"),
        MediaUsageRef(kind="blog", entity_id=BLOG_ID, title="Blog B", location="content"),
    ]
    repo = _repo_with(refs=refs)
    result = _use_case(repo).execute(ASSET_ID)

    assert result.usage_count == 5
    assert len(result.references) == 5


# ── use-case: usage_count always matches len(references) ─────────────────────

def test_usage_count_equals_len_references() -> None:
    """usage_count is derived from len(refs), not a separate COUNT query."""
    refs = [
        MediaUsageRef(kind="project", entity_id=PROJECT_ID, title="P", location="thumbnail"),
        MediaUsageRef(kind="project", entity_id=PROJECT_ID, title="P", location="hero block"),
        MediaUsageRef(kind="blog", entity_id=BLOG_ID, title="B", location="cover"),
    ]
    repo = _repo_with(refs=refs)
    result = _use_case(repo).execute(ASSET_ID)

    assert result.usage_count == len(result.references) == 3


# ── use-case: YouTube asset (no public_id) ────────────────────────────────────

def test_youtube_asset_with_no_public_id_skips_find_usage() -> None:
    """Assets with no public_id (e.g. YouTube imports) cannot be embedded in
    project/blog content via a Cloudinary URL, so find_usage is skipped."""
    yt_asset = _asset(
        source_type="youtube",
        public_id=None,
        cloudinary_url=None,
        external_id="dQw4w9WgXcQ",
        thumbnail_url="https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    )
    repo = _repo_with(asset=_item(yt_asset))
    result = _use_case(repo).execute(ASSET_ID)

    repo.find_usage.assert_not_called()
    assert result.usage_count == 0
    assert result.references == []


# ── use-case: title can be None (untitled project) ───────────────────────────

def test_reference_with_none_title_is_allowed() -> None:
    ref = MediaUsageRef(kind="project", entity_id=PROJECT_ID, title=None, location="thumbnail")
    repo = _repo_with(refs=[ref])
    result = _use_case(repo).execute(ASSET_ID)

    assert result.references[0].title is None


# ── HTTP layer: auth guard ────────────────────────────────────────────────────

def test_usage_endpoint_requires_auth() -> None:
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(f"/api/v1/admin/media/{ASSET_ID}/usage")
    assert resp.status_code == 401


# ── HTTP layer: 422 on bad UUID ───────────────────────────────────────────────

def test_usage_endpoint_rejects_non_uuid_path_param() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: Mock()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/media/not-a-uuid/usage")
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)


# ── HTTP layer: 404 when asset not found ─────────────────────────────────────

def test_usage_endpoint_returns_404_for_unknown_asset() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    mock_uc = Mock()
    mock_uc.execute.side_effect = NotFoundError(f"No media asset with id {ASSET_ID}")

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/admin/media/{ASSET_ID}/usage")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "MEDIA_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)


# ── HTTP layer: 200 + empty references ───────────────────────────────────────

def test_usage_endpoint_returns_200_with_empty_references() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    mock_uc = Mock()
    mock_uc.execute.return_value = MediaUsageResult(
        asset_id=ASSET_ID,
        usage_count=0,
        references=[],
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/admin/media/{ASSET_ID}/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset_id"] == str(ASSET_ID)
        assert body["usage_count"] == 0
        assert body["references"] == []
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)


# ── HTTP layer: 200 + full in-use shape ──────────────────────────────────────

def test_usage_endpoint_returns_200_with_references() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    references = [
        UsageReferenceView(
            kind="project",
            id=str(PROJECT_ID),
            title="Jerry — Public AI Assistant",
            location="thumbnail",
            url=f"/admin/projects/{PROJECT_ID}",
        ),
        UsageReferenceView(
            kind="project",
            id=str(PROJECT_ID),
            title="Jerry — Public AI Assistant",
            location="image block",
            url=f"/admin/projects/{PROJECT_ID}",
        ),
        UsageReferenceView(
            kind="blog",
            id=str(BLOG_ID),
            title="My First Post",
            location="cover",
            url=f"/admin/blogs/{BLOG_ID}",
        ),
    ]

    mock_uc = Mock()
    mock_uc.execute.return_value = MediaUsageResult(
        asset_id=ASSET_ID,
        usage_count=3,
        references=references,
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/admin/media/{ASSET_ID}/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asset_id"] == str(ASSET_ID)
        assert body["usage_count"] == 3
        assert len(body["references"]) == 3

        # Verify full reference shape from spec
        first = body["references"][0]
        assert first["kind"] == "project"
        assert first["id"] == str(PROJECT_ID)
        assert first["title"] == "Jerry — Public AI Assistant"
        assert first["location"] == "thumbnail"
        assert first["url"] == f"/admin/projects/{PROJECT_ID}"

        third = body["references"][2]
        assert third["kind"] == "blog"
        assert third["url"] == f"/admin/blogs/{BLOG_ID}"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)


# ── HTTP layer: usage_count matches references length in response ─────────────

def test_http_usage_count_matches_references_length() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    refs = [
        UsageReferenceView(kind="project", id=str(PROJECT_ID), title="P", location="thumbnail", url="/admin/projects/x"),
        UsageReferenceView(kind="og", id=str(BLOG_ID), title="B", location="og:image", url="/admin/blogs/y"),
    ]
    mock_uc = Mock()
    mock_uc.execute.return_value = MediaUsageResult(
        asset_id=ASSET_ID, usage_count=2, references=refs
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        body = client.get(f"/api/v1/admin/media/{ASSET_ID}/usage").json()
        assert body["usage_count"] == len(body["references"])
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)


# ── HTTP layer: reference with null title is serialised correctly ─────────────

def test_http_serialises_null_title_in_reference() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    mock_uc = Mock()
    mock_uc.execute.return_value = MediaUsageResult(
        asset_id=ASSET_ID,
        usage_count=1,
        references=[
            UsageReferenceView(
                kind="project", id=str(PROJECT_ID), title=None,
                location="thumbnail", url=f"/admin/projects/{PROJECT_ID}"
            )
        ],
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        body = client.get(f"/api/v1/admin/media/{ASSET_ID}/usage").json()
        assert body["references"][0]["title"] is None
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)


# ── HTTP layer: use_case.execute is called with the path UUID ─────────────────

def test_http_passes_uuid_to_use_case() -> None:
    from app.main import app
    from app.api.v1.dependencies.auth import get_current_admin
    from app.api.v1.dependencies.providers import get_media_usage

    mock_uc = Mock()
    mock_uc.execute.return_value = MediaUsageResult(
        asset_id=ASSET_ID, usage_count=0, references=[]
    )

    app.dependency_overrides[get_current_admin] = lambda: Mock()
    app.dependency_overrides[get_media_usage] = lambda: mock_uc
    try:
        client = TestClient(app, raise_server_exceptions=False)
        client.get(f"/api/v1/admin/media/{ASSET_ID}/usage")
        mock_uc.execute.assert_called_once_with(ASSET_ID)
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_media_usage, None)

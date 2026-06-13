"""Tests for API 16 — GET /admin/media (List Media Assets).

Covers: pagination maths, filter routing, search escaping, edge cases from spec,
resource_type validation, folder_stats always reflecting the full library, and
the total_pages calculation.
"""
from __future__ import annotations

import datetime
import math
import uuid
from unittest.mock import Mock, patch

import pytest

from app.application.dtos.media import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    ListMediaQuery,
    ListMediaResult,
    MediaAssetView,
)
from app.application.use_cases.media.list_media import ListMedia
from app.domain.entities.media_asset import MediaAsset
from app.domain.exceptions import ValidationError
from app.domain.repositories.media_asset_repository import (
    MediaAssetListItem,
    MediaListPage,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _asset(**overrides) -> MediaAsset:
    defaults = {
        "id": uuid.uuid4(),
        "cloudinary_url": "https://res.cloudinary.com/udit/image/upload/v1/projects/thumbnails/img.jpg",
        "public_id": "projects/thumbnails/img",
        "resource_type": "image",
        "format": "jpg",
        "width": 1200,
        "height": 630,
        "file_size": 214732,
        "file_name": "img.jpg",
        "folder": "projects/thumbnails",
        "alt_text": "A thumbnail",
        "source_type": "cloudinary",
        "external_id": None,
        "thumbnail_url": None,
        "video_title": None,
        "video_duration_seconds": None,
        "file_hash": "abc123",
        "is_orphan": False,
        "uploaded_by": uuid.uuid4(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    return MediaAsset(**defaults)


def _list_item(asset: MediaAsset | None = None, name: str | None = "Admin") -> MediaAssetListItem:
    return MediaAssetListItem(asset=asset or _asset(), uploaded_by_name=name)


def _repo_returning(items: list[MediaAssetListItem], total: int) -> Mock:
    repo = Mock()
    repo.list.return_value = MediaListPage(items=items, total=total)
    repo.folder_stats.return_value = {"projects/thumbnails": 8, "all": 8}
    repo.type_stats.return_value = {"image": 8}
    return repo


def _use_case(repo: Mock) -> ListMedia:
    return ListMedia(repo=repo)


# ── basic success ─────────────────────────────────────────────────────────────

def test_returns_assets_and_correct_total_pages() -> None:
    items = [_list_item() for _ in range(5)]
    repo = _repo_returning(items, total=84)
    result = _use_case(repo).execute(ListMediaQuery(page=1, limit=20))

    assert len(result.assets) == 5
    assert result.total == 84
    assert result.page == 1
    assert result.limit == 20
    assert result.total_pages == math.ceil(84 / 20)   # 5


def test_total_pages_rounds_up() -> None:
    repo = _repo_returning([], total=21)
    result = _use_case(repo).execute(ListMediaQuery(page=1, limit=20))
    assert result.total_pages == 2      # ceil(21/20) = 2


def test_total_pages_exact_division() -> None:
    repo = _repo_returning([], total=40)
    result = _use_case(repo).execute(ListMediaQuery(page=1, limit=20))
    assert result.total_pages == 2      # 40/20 = exactly 2


# ── edge case 1: empty library ────────────────────────────────────────────────

def test_empty_library_returns_zero_total_pages() -> None:
    repo = _repo_returning([], total=0)
    repo.folder_stats.return_value = {"all": 0}
    repo.type_stats.return_value = {}
    result = _use_case(repo).execute(ListMediaQuery())

    assert result.assets == []
    assert result.total == 0
    assert result.total_pages == 0


# ── edge case 2: folder filter that matches nothing ───────────────────────────

def test_unknown_folder_returns_empty_assets_but_global_folder_stats() -> None:
    repo = _repo_returning([], total=0)
    repo.folder_stats.return_value = {"projects/thumbnails": 8, "all": 8}
    result = _use_case(repo).execute(ListMediaQuery(folder="nonexistent/folder"))

    assert result.assets == []
    assert result.total == 0
    # folder_stats reflects global counts, not the filtered result
    assert result.folder_stats == {"projects/thumbnails": 8, "all": 8}


# ── edge case 3: page beyond total_pages ─────────────────────────────────────

def test_page_beyond_total_pages_returns_empty_assets_with_correct_total() -> None:
    repo = _repo_returning([], total=15)
    result = _use_case(repo).execute(ListMediaQuery(page=100, limit=20))

    assert result.assets == []
    assert result.total == 15
    assert result.total_pages == 1     # ceil(15/20) = 1


# ── edge case 4: limit clamped to MAX_LIMIT ───────────────────────────────────

def test_limit_exceeding_max_is_clamped_to_100() -> None:
    repo = _repo_returning([], total=200)
    result = _use_case(repo).execute(ListMediaQuery(limit=9999))

    # The use case clamps; the repo receives the capped value.
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["limit"] == MAX_LIMIT
    assert result.limit == MAX_LIMIT


# ── edge case 5: invalid resource_type raises ValidationError ─────────────────

def test_invalid_resource_type_raises_validation_error() -> None:
    repo = _repo_returning([], total=0)
    with pytest.raises(ValidationError, match="Invalid resource_type"):
        _use_case(repo).execute(ListMediaQuery(resource_type="gif"))


def test_valid_resource_types_are_accepted() -> None:
    for rt in ("image", "video", "raw"):
        repo = _repo_returning([], total=0)
        result = _use_case(repo).execute(ListMediaQuery(resource_type=rt))
        assert result.total == 0    # no error raised


# ── edge case 6: search escaping ─────────────────────────────────────────────

def test_search_with_like_special_chars_is_passed_through_to_repo() -> None:
    """The use case forwards the search to the repo as-is; escaping is the
    repo's responsibility (SQL layer). We verify the value is not swallowed."""
    repo = _repo_returning([], total=0)
    _use_case(repo).execute(ListMediaQuery(search="%_special%"))
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["search"] == "%_special%"


def test_empty_search_string_is_treated_as_no_search() -> None:
    repo = _repo_returning([], total=0)
    _use_case(repo).execute(ListMediaQuery(search="   "))
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["search"] is None


# ── edge case 7: short search strings are allowed ────────────────────────────

def test_one_char_search_is_forwarded() -> None:
    repo = _repo_returning([], total=0)
    _use_case(repo).execute(ListMediaQuery(search="a"))
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["search"] == "a"


# ── edge case 8: folder_stats is always global ───────────────────────────────

def test_folder_stats_is_independent_of_filters() -> None:
    global_stats = {"projects/thumbnails": 8, "blog/covers": 12, "all": 20}
    repo = _repo_returning([], total=0)
    repo.folder_stats.return_value = global_stats
    result = _use_case(repo).execute(
        ListMediaQuery(folder="projects/thumbnails", resource_type="image")
    )
    assert result.folder_stats == global_stats
    # folder_stats was called without any filter args
    repo.folder_stats.assert_called_once_with()


# ── page normalisation ────────────────────────────────────────────────────────

def test_page_below_one_is_normalised_to_one() -> None:
    """The use case clamps page to 1 — the HTTP layer also enforces ge=1 via
    FastAPI's Query, but the use case is the authoritative clamping point."""
    repo = _repo_returning([], total=0)
    result = _use_case(repo).execute(ListMediaQuery(page=-5))
    assert result.page == 1
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["offset"] == 0


def test_default_limit_is_used_when_not_provided() -> None:
    repo = _repo_returning([], total=0)
    result = _use_case(repo).execute(ListMediaQuery())
    assert result.limit == DEFAULT_LIMIT


# ── sort validation ───────────────────────────────────────────────────────────

def test_invalid_sort_by_raises_validation_error() -> None:
    repo = _repo_returning([], total=0)
    with pytest.raises(ValidationError, match="Invalid sort_by"):
        _use_case(repo).execute(ListMediaQuery(sort_by="unknown"))


def test_invalid_order_raises_validation_error() -> None:
    repo = _repo_returning([], total=0)
    with pytest.raises(ValidationError, match="Invalid order"):
        _use_case(repo).execute(ListMediaQuery(order="random"))


# ── pagination offset calculation ─────────────────────────────────────────────

def test_offset_is_calculated_correctly_for_page_3() -> None:
    repo = _repo_returning([], total=100)
    _use_case(repo).execute(ListMediaQuery(page=3, limit=10))
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["offset"] == 20  # (3-1) * 10


# ── response shape ────────────────────────────────────────────────────────────

def test_result_includes_type_stats() -> None:
    repo = _repo_returning([], total=0)
    repo.type_stats.return_value = {"image": 5, "video": 2}
    result = _use_case(repo).execute(ListMediaQuery())
    assert result.type_stats == {"image": 5, "video": 2}

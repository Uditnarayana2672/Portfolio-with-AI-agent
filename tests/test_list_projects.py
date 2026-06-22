"""Tests for API 19 — GET /admin/projects (List Projects).

Covers: empty list, status filter, search filter, pagination, page clamping,
empty search normalisation, invalid status rejection.
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import Mock

import pytest

from app.application.dtos.project import (
    ListProjectsCommand,
    ListProjectsResult,
    ProjectSummaryResult,
)
from app.application.use_cases.projects.list_projects import ListProjects
from app.domain.entities.project import Project
from app.domain.exceptions import ValidationError


# ── helpers ───────────────────────────────────────────────────────────────────

_AUTHOR = uuid.uuid4()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _project(**overrides) -> Project:
    defaults = {
        "id": uuid.uuid4(),
        "title": "My Project",
        "slug": "my-project",
        "excerpt": "A test project",
        "thumbnail_url": None,
        "tech_stack": ["Python", "FastAPI"],
        "template_id": "narrative",
        "github_url": None,
        "demo_url": None,
        "status": "draft",
        "visibility": "public",
        "is_featured": False,
        "views": 0,
        "seo": {},
        "author_id": _AUTHOR,
        "published_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    return Project(**defaults)


def _repo_returning(projects: list[Project], total: int) -> Mock:
    repo = Mock()
    reactions = [0] * len(projects)
    repo.list_projects.return_value = (projects, reactions, total)
    return repo


def _use_case(repo: Mock) -> ListProjects:
    return ListProjects(repo=repo)


# ── basic success ─────────────────────────────────────────────────────────────

def test_returns_empty_list_for_no_projects() -> None:
    repo = _repo_returning([], 0)
    result = _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR))

    assert result.items == []
    assert result.total == 0
    assert result.page == 1
    assert result.page_size == 20


def test_returns_items_and_total() -> None:
    projects = [_project() for _ in range(3)]
    repo = _repo_returning(projects, 3)
    result = _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR))

    assert len(result.items) == 3
    assert result.total == 3


def test_result_items_have_expected_fields() -> None:
    p = _project(title="Portfolio Site", status="published")
    repo = _repo_returning([p], 1)
    result = _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR))

    item = result.items[0]
    assert item.id == p.id
    assert item.title == "Portfolio Site"
    assert item.status == "published"


# ── status filter ─────────────────────────────────────────────────────────────

def test_status_filter_forwarded_to_repo() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, status="published"))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["status_filter"] == "published"


def test_none_status_passes_none_to_repo() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, status=None))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["status_filter"] is None


def test_archived_status_is_valid() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, status="archived"))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["status_filter"] == "archived"


def test_invalid_status_raises_validation_error() -> None:
    repo = _repo_returning([], 0)
    with pytest.raises(ValidationError, match="status"):
        _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, status="invalid"))


# ── search filter ─────────────────────────────────────────────────────────────

def test_search_forwarded_to_repo() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, search="portfolio"))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["search"] == "portfolio"


def test_empty_search_string_treated_as_none() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, search="   "))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["search"] is None


def test_none_search_passes_none_to_repo() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, search=None))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["search"] is None


# ── pagination ────────────────────────────────────────────────────────────────

def test_pagination_params_forwarded_to_repo() -> None:
    repo = _repo_returning([], 0)
    _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, page=3, page_size=10))
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["page"] == 3
    assert call_kwargs["page_size"] == 10


def test_page_below_one_clamped_to_one() -> None:
    repo = _repo_returning([], 0)
    result = _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, page=-5))
    assert result.page == 1
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["page"] == 1


def test_page_size_capped_at_100() -> None:
    repo = _repo_returning([], 0)
    result = _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, page_size=9999))
    assert result.page_size == 100
    _, call_kwargs = repo.list_projects.call_args
    assert call_kwargs["page_size"] == 100


def test_result_echoes_page_and_page_size() -> None:
    repo = _repo_returning([], 0)
    result = _use_case(repo).execute(ListProjectsCommand(author_id=_AUTHOR, page=2, page_size=5))
    assert result.page == 2
    assert result.page_size == 5

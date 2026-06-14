"""Tests for GET /admin/forms (List Forms).

Covers: empty result, basic list, search forwarding, empty search normalisation.
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import Mock

from app.application.use_cases.forms.list_forms import ListForms
from app.domain.entities.form import Form


# ── helpers ───────────────────────────────────────────────────────────────────

_AUTHOR = uuid.uuid4()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _form(**overrides) -> Form:
    defaults = {
        "id": uuid.uuid4(),
        "author_id": _AUTHOR,
        "name": "Contact Form",
        "form_type": "contact",
        "config": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    return Form(**defaults)


def _repo_returning(forms: list[Form]) -> Mock:
    repo = Mock()
    repo.list.return_value = forms
    return repo


def _use_case(repo: Mock) -> ListForms:
    return ListForms(repo=repo)


# ── basic success ─────────────────────────────────────────────────────────────

def test_returns_empty_list_when_no_forms() -> None:
    repo = _repo_returning([])
    result = _use_case(repo).execute(author_id=_AUTHOR)
    assert result == []


def test_returns_all_forms_for_author() -> None:
    forms = [_form() for _ in range(3)]
    repo = _repo_returning(forms)
    result = _use_case(repo).execute(author_id=_AUTHOR)
    assert len(result) == 3


def test_result_fields_match_entity() -> None:
    f = _form(name="Bug report form", form_type="feedback")
    repo = _repo_returning([f])
    result = _use_case(repo).execute(author_id=_AUTHOR)
    assert result[0].name == "Bug report form"
    assert result[0].form_type == "feedback"
    assert result[0].id == f.id


# ── search ────────────────────────────────────────────────────────────────────

def test_search_forwarded_to_repo() -> None:
    repo = _repo_returning([])
    _use_case(repo).execute(author_id=_AUTHOR, search="contact")
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["search"] == "contact"


def test_empty_search_treated_as_none() -> None:
    repo = _repo_returning([])
    _use_case(repo).execute(author_id=_AUTHOR, search="   ")
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["search"] is None


def test_none_search_passes_none_to_repo() -> None:
    repo = _repo_returning([])
    _use_case(repo).execute(author_id=_AUTHOR, search=None)
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["search"] is None


def test_author_id_forwarded_to_repo() -> None:
    repo = _repo_returning([])
    _use_case(repo).execute(author_id=_AUTHOR)
    _, call_kwargs = repo.list.call_args
    assert call_kwargs["author_id"] == _AUTHOR

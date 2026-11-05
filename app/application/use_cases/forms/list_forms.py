"""ListForms use case (application layer)."""
from __future__ import annotations

import uuid

from app.domain.entities.form import Form
from app.domain.repositories.form_repository import FormRepository


class ListForms:
    def __init__(self, repo: FormRepository) -> None:
        self._repo = repo

    def execute(self, author_id: uuid.UUID, search: str | None = None) -> list[Form]:
        search = search.strip() if search else None
        search = search or None
        return self._repo.list(author_id=author_id, search=search)

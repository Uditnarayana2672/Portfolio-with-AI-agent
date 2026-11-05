"""Fixed form types (infrastructure layer).

The site has one real form, and these are the reasons a visitor can use it for.
Submissions land in the admin Inbox. There is no form builder or forms table.
"""
from __future__ import annotations

import datetime
import uuid

from app.domain.entities.form import Form
from app.domain.repositories.form_repository import FormRepository

_EPOCH = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
_FORMS = (
    ("contact", "Contact / general enquiry", "contact"),
    ("discovery", "Project discovery call request", "discovery"),
    ("feedback", "Feedback", "feedback"),
)


class StaticFormRepository(FormRepository):
    def list(self, author_id: uuid.UUID, search: str | None) -> list[Form]:
        rows = [self._form(*row, author_id) for row in _FORMS]
        if search:
            rows = [f for f in rows if search.lower() in f.name.lower()]
        return rows

    def get(self, id) -> Form | None:
        return next((self._form(*row, uuid.UUID(int=0)) for row in _FORMS if row[0] == str(id)), None)

    @staticmethod
    def _form(form_id: str, name: str, form_type: str, author_id: uuid.UUID) -> Form:
        return Form(
            id=form_id, author_id=author_id, name=name, form_type=form_type,
            config={}, created_at=_EPOCH, updated_at=_EPOCH,
        )

"""FormRepository port (domain layer).

Abstract contract for persisting/querying forms. The application layer
depends on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.domain.entities.form import Form


class FormRepository(ABC):
    @abstractmethod
    def list(self, author_id: uuid.UUID, search: str | None) -> list[Form]:
        """Return forms for the given author ordered by created_at desc.
        ``search`` filters by name (ILIKE); None means no filter."""

    @abstractmethod
    def get(self, id: uuid.UUID) -> Form | None:
        """Return a single form by ID, or None if not found."""

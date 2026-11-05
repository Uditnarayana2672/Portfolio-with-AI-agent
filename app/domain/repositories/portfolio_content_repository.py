"""PortfolioContentRepository port (domain layer).

Contract for the single-row portfolio content document. The SQLAlchemy
implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.domain.entities.portfolio_content import PortfolioContent


class PortfolioContentRepository(ABC):
    @abstractmethod
    def get(self) -> PortfolioContent | None:
        """Return the document, or None if the seed row is missing."""

    @abstractmethod
    def update(
        self, *, expected_version: int, content: dict, updated_by: uuid.UUID
    ) -> PortfolioContent | None:
        """Replace the document and bump its version, only if the stored version
        still equals ``expected_version``. Returns None when it does not, so two
        concurrent saves can never both succeed."""

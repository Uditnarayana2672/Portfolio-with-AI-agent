"""ActivityLogRepository port (domain layer).

Abstract contract for recording audit-trail entries (the `activity_log` table).
Use cases depend on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class ActivityLogRepository(ABC):
    @abstractmethod
    def record(
        self,
        *,
        action_type: str,
        description: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        entity_title: str | None = None,
        performed_by: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Append one activity entry. ``action_type`` is a domain string (e.g.
        ``"media_uploaded"``) that the adapter maps to the DB enum."""

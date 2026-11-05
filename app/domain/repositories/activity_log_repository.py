"""ActivityLogRepository port (domain layer).

Abstract contract for recording audit-trail entries (the `activity_log` table).
Use cases depend on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import datetime
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityEntry:
    id: uuid.UUID
    action_type: str
    description: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_title: str | None
    performed_by: uuid.UUID | None
    created_at: datetime.datetime
    entity_exists: bool  # False once the referenced row has been deleted


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

    @abstractmethod
    def list_recent(self, limit: int) -> list[ActivityEntry]:
        """Return the latest entries, newest first, each flagged with whether
        the entity it refers to still exists."""

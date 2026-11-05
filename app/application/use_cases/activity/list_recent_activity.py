"""Recent activity for the admin Overview page (application layer)."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

from app.domain.repositories.activity_log_repository import ActivityEntry, ActivityLogRepository

_CATEGORIES = {
    "project": "project",
    "blog_post": "blog",
    "media_asset": "media",
    "portfolio": "portfolio",
}


@dataclass(frozen=True)
class ActivityView:
    id: uuid.UUID
    action_type: str
    category: str
    description: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_title: str | None
    actor: str
    link: str | None
    created_at: datetime.datetime


def _link(entry: ActivityEntry) -> str | None:
    """Admin deep link, or None when there is nothing left to open."""
    if not entry.entity_exists:
        return None
    if entry.entity_type == "project":
        return f"/admin/projects/{entry.entity_id}/edit"
    if entry.entity_type == "blog_post":
        return f"/admin/blogs/{entry.entity_id}/edit"
    if entry.entity_type == "media_asset":
        return "/admin/media"
    return None


class ListRecentActivity:
    def __init__(self, repo: ActivityLogRepository) -> None:
        self._repo = repo

    def execute(self, limit: int) -> list[ActivityView]:
        return [
            ActivityView(
                id=e.id,
                action_type=e.action_type,
                category=_CATEGORIES.get(e.entity_type or "", "other"),
                description=e.description,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                entity_title=e.entity_title,
                actor="you" if e.performed_by else "system",
                link=_link(e),
                created_at=e.created_at,
            )
            for e in self._repo.list_recent(limit)
        ]

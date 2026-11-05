"""HTTP response schemas for the activity stream (presentation layer)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.api.v1.schemas.blog import UtcDatetime


class ActivityItemResponse(BaseModel):
    id: uuid.UUID
    action_type: str
    category: str
    description: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_title: str | None
    actor: str
    link: str | None
    created_at: UtcDatetime


class ActivityListResponse(BaseModel):
    items: list[ActivityItemResponse]

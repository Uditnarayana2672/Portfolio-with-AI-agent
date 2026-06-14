"""HTTP response schemas for form endpoints (presentation layer)."""
from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, field_serializer


class FormSummaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    form_type: str
    created_at: datetime.datetime

    @field_serializer("created_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

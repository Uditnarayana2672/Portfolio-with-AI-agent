"""DTOs for media use cases (application layer).

Plain dataclasses decoupled from both the ORM and the HTTP schemas.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

# Allowed query values + pagination bounds (the single source of truth the
# use case validates against).
VALID_SORT_BY = ("created_at", "file_size", "file_name")
VALID_ORDER = ("asc", "desc")
VALID_RESOURCE_TYPES = ("image", "video", "raw")
DEFAULT_LIMIT = 30
MAX_LIMIT = 100


@dataclass
class ListMediaQuery:
    """Raw query input, as received from the HTTP layer (unvalidated)."""

    folder: str | None = None
    resource_type: str | None = None
    search: str | None = None
    page: int = 1
    limit: int = DEFAULT_LIMIT
    sort_by: str = "created_at"
    order: str = "desc"


@dataclass
class MediaAssetView:
    """One asset as returned by the list endpoint (response shape)."""

    id: uuid.UUID
    cloudinary_url: str | None
    public_id: str | None
    resource_type: str
    format: str | None
    width: int | None
    height: int | None
    file_size: int | None
    file_name: str | None
    folder: str
    alt_text: str | None
    source_type: str
    thumbnail_url: str | None
    video_duration_seconds: int | None
    is_orphan: bool
    cdn_status: str            # 'ok' | 'missing'
    uploaded_by: uuid.UUID | None
    uploaded_by_name: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


@dataclass
class ListMediaResult:
    assets: list[MediaAssetView]
    total: int
    page: int
    limit: int
    folder_stats: dict[str, int] = field(default_factory=dict)
    type_stats: dict[str, int] = field(default_factory=dict)

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

# ── Upload rules (single source of truth the UploadMedia use case enforces) ──
# Whitelisted extensions, in the exact order surfaced in the 415 error body.
ALLOWED_EXTENSIONS = ("jpg", "png", "webp", "gif", "mp4", "mov", "webm", "pdf")
# Each whitelisted extension → its domain resource_type.
EXTENSION_RESOURCE_TYPE = {
    "jpg": "image",
    "png": "image",
    "webp": "image",
    "gif": "image",
    "mp4": "video",
    "mov": "video",
    "webm": "video",
    "pdf": "raw",
}
# Size caps by resource_type: 20 MB for images/raw, 200 MB for video.
IMAGE_MAX_BYTES = 20 * 1024 * 1024   # 20 MB (20,971,520)
VIDEO_MAX_BYTES = 200 * 1024 * 1024  # 200 MB (209,715,200)
# Backoff (seconds) between Cloudinary upload attempts; len → max attempts.
UPLOAD_RETRY_BACKOFF = (0.5, 2.0, 8.0)


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


@dataclass
class MediaAssetDetailResult:
    """One asset for the drawer: the full §3.1 view plus a usage total."""

    asset: MediaAssetView
    usage_count: int


@dataclass
class StorageStatsView:
    """The Cloudinary storage banner: bytes used vs. the plan's quota."""

    used_bytes: int
    quota_bytes: int
    used_human: str
    quota_human: str
    percent_used: int
    plan: str


@dataclass
class CleanupStatsView:
    """Summary of the most recent nightly orphan-cleanup run."""

    ran_at: datetime.datetime
    freed_bytes: int
    freed_human: str
    orphans_removed: int


@dataclass
class UploadMediaCommand:
    """Raw upload input handed from the HTTP layer to the use case."""

    content: bytes
    original_filename: str
    folder: str
    uploaded_by: uuid.UUID
    resource_type: str | None = None  # None → inferred from the extension
    file_name: str | None = None      # display-name override
    alt_text: str | None = None


@dataclass
class ImportUrlCommand:
    """Raw input for importing an asset from a remote URL."""

    url: str
    folder: str
    uploaded_by: uuid.UUID
    alt_text: str | None = None


@dataclass
class UploadedAssetView:
    """The asset projection returned by the upload/import endpoints.

    The ``source_type``/``external_id``/``video_*``/``thumbnail_url`` fields are
    only meaningful for a registered remote video (YouTube import); the upload
    endpoint serialises a subset and ignores them.
    """

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
    file_hash: str | None
    uploaded_by: uuid.UUID | None
    created_at: datetime.datetime
    source_type: str = "cloudinary"
    external_id: str | None = None
    thumbnail_url: str | None = None
    video_title: str | None = None
    video_duration_seconds: int | None = None


@dataclass
class UploadMediaResult:
    duplicate: bool
    asset: UploadedAssetView
    # None for the duplicate response (the key is omitted entirely there).
    renamed: bool | None = None
    rename_note: str | None = None


@dataclass
class MediaStatsResult:
    """Powers the dashboard's 5 ministat cards + the storage banner."""

    total_assets: int
    added_today: int
    counts: dict[str, int]
    storage: StorageStatsView
    # None until a cleanup-run history table exists to source it from.
    last_cleanup: CleanupStatsView | None = None

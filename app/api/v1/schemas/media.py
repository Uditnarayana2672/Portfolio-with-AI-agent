"""HTTP request/response schemas for media endpoints (presentation layer)."""
from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    cdn_status: str
    uploaded_by: uuid.UUID | None
    uploaded_by_name: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        # Emit UTC with a trailing "Z" (e.g. 2026-05-27T11:48:00Z) per the contract.
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MediaAssetDetailResponse(MediaAssetResponse):
    """The §3.1 asset shape plus a convenience usage total for the drawer."""

    usage_count: int


class MediaListResponse(BaseModel):
    assets: list[MediaAssetResponse]
    total: int
    page: int
    limit: int
    folder_stats: dict[str, int]
    type_stats: dict[str, int]


class StorageStatsResponse(BaseModel):
    used_bytes: int
    quota_bytes: int
    used_human: str
    quota_human: str
    percent_used: int
    plan: str


class CleanupStatsResponse(BaseModel):
    ran_at: datetime.datetime
    freed_bytes: int
    freed_human: str
    orphans_removed: int

    @field_serializer("ran_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MediaStatsResponse(BaseModel):
    total_assets: int
    added_today: int
    counts: dict[str, int]
    storage: StorageStatsResponse
    last_cleanup: CleanupStatsResponse | None = None


class UploadedAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @field_serializer("created_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UploadMediaResponse(BaseModel):
    duplicate: bool
    asset: UploadedAssetResponse
    # Omitted (via response_model_exclude_none) on the duplicate response, and
    # rename_note is omitted unless a collision actually triggered a rename.
    renamed: bool | None = None
    rename_note: str | None = None


class ImportUrlRequest(BaseModel):
    url: str = Field(..., min_length=1, description="http(s) URL or a YouTube link")
    folder: str = Field(..., min_length=1)
    alt_text: str | None = None

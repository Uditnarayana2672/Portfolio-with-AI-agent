"""HTTP request/response schemas for the blog editor (presentation layer).

Shapes follow "New Blog Post API.md" §3. Responses are built from the
application DTOs with ``model_validate(..., from_attributes=True)``.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer


def _utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Emit UTC with a trailing "Z" (e.g. 2026-05-27T11:48:00Z), same as media.
UtcDatetime = Annotated[datetime.datetime, PlainSerializer(_utc, return_type=str, when_used="json")]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── requests ─────────────────────────────────────────────────────────────────


class SeoInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meta_title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None


class PostWritable(BaseModel):
    """Any subset of the editor's fields. Unknown keys are ignored so an older
    client never breaks; omitted keys are left unchanged."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    subtitle: str | None = None
    slug: str | None = None
    slug_locked: bool | None = None
    content: dict[str, Any] | None = None
    excerpt: str | None = None
    cover_asset_id: uuid.UUID | None = None
    og_asset_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    tags: list[str] | None = None
    allow_comments: bool | None = None
    seo: SeoInput | None = None


class UpdatePostRequest(PostWritable):
    version: int = Field(..., ge=1)


class VersionRequest(BaseModel):
    version: int = Field(..., ge=1)


class ScheduleRequest(BaseModel):
    version: int = Field(..., ge=1)
    scheduled_at: datetime.datetime


class CreateRevisionRequest(BaseModel):
    version: int = Field(..., ge=1)
    label: str | None = Field(default=None, max_length=60)


class CreateCategoryRequest(BaseModel):
    name: str
    description: str | None = None


class ResolveEmbedRequest(BaseModel):
    url: str


# ── shared response pieces ───────────────────────────────────────────────────


class MediaRefResponse(_Out):
    id: uuid.UUID
    url: str | None
    public_id: str | None
    resource_type: str
    source_type: str
    width: int | None
    height: int | None
    alt_text: str | None
    thumbnail_url: str | None
    external_id: str | None = None
    video_title: str | None = None
    video_duration_seconds: int | None = None


class CategoryResponse(_Out):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    sort_order: int
    post_count: int = 0
    published_count: int = 0


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]


class ChecklistItemResponse(_Out):
    key: str
    label: str
    level: str
    passed: bool
    message: str | None
    paths: list[str]


class ChecklistResponse(_Out):
    can_publish: bool
    blocker_count: int
    warning_count: int
    items: list[ChecklistItemResponse]


class StatsResponse(_Out):
    word_count: int
    reading_time_min: int
    block_count: int
    image_count: int


class SeoResponse(_Out):
    meta_title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None


class SeoEffectiveResponse(_Out):
    meta_title: str
    meta_description: str
    canonical_url: str
    og_image_url: str | None


class AuthorResponse(_Out):
    id: uuid.UUID
    name: str
    avatar_url: str | None


class PostDetailResponse(_Out):
    id: uuid.UUID
    version: int
    title: str
    subtitle: str | None
    slug: str
    slug_locked: bool
    content: dict[str, Any]
    excerpt: str | None
    cover: MediaRefResponse | None
    og_image: MediaRefResponse | None
    category: CategoryResponse | None
    tags: list[str]
    allow_comments: bool
    seo: SeoResponse
    seo_effective: SeoEffectiveResponse
    status: str
    status_label: str
    scheduled_at: UtcDatetime | None
    published_at: UtcDatetime | None
    last_published_at: UtcDatetime | None
    has_unpublished_changes: bool
    public_url: str | None
    schedule_error: str | None
    stats: StatsResponse
    checklist: ChecklistResponse
    author: AuthorResponse | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class SaveWarningResponse(_Out):
    code: str
    message: str
    path: str | None = None


class SaveResultResponse(_Out):
    id: uuid.UUID
    version: int
    updated_at: UtcDatetime
    slug: str
    slug_adjusted: bool
    stats: StatsResponse
    has_unpublished_changes: bool
    checklist: ChecklistResponse
    warnings: list[SaveWarningResponse]


class SlugCheckResponse(_Out):
    input: str
    slug: str
    available: bool
    reason: str | None
    suggested: str | None


# ── revisions ────────────────────────────────────────────────────────────────


class RevisionAuthor(BaseModel):
    id: uuid.UUID
    name: str | None


class RevisionSummaryResponse(BaseModel):
    id: uuid.UUID
    kind: str
    label: str | None
    word_count: int
    created_by: RevisionAuthor | None
    created_at: UtcDatetime
    is_live: bool


class RevisionDetailResponse(RevisionSummaryResponse):
    snapshot: dict[str, Any]
    content_html: str


class RevisionListResponse(BaseModel):
    items: list[RevisionSummaryResponse]
    total: int
    page: int
    limit: int
    total_pages: int


# ── preview ──────────────────────────────────────────────────────────────────


class TocEntryResponse(_Out):
    id: str
    text: str
    level: int
    number: str | None


class PublicPostResponse(_Out):
    title: str
    subtitle: str | None
    slug: str
    url: str
    cover: dict[str, Any] | None
    category: dict[str, Any] | None
    tags: list[dict[str, Any]]
    author: dict[str, Any]
    published_at: UtcDatetime | None
    updated_at: UtcDatetime
    reading_time_min: int
    word_count: int
    toc: list[TocEntryResponse]
    content_html: str
    head: dict[str, Any]


class PreviewResponse(_Out):
    source: str
    post_id: uuid.UUID
    version: int
    status: str
    post: PublicPostResponse
    search_preview: dict[str, Any]
    social_preview: dict[str, Any]
    checklist: ChecklistResponse
    generated_at: UtcDatetime


# ── taxonomy & helpers ───────────────────────────────────────────────────────


class TagCount(BaseModel):
    tag: str
    count: int


class TagListResponse(BaseModel):
    items: list[TagCount]


class ResolvedEmbedResponse(_Out):
    provider: str
    original_url: str
    embed_url: str
    height: int
    title: str | None = None
    thumbnail_url: str | None = None


class LinkTargetResponse(_Out):
    type: str
    id: str
    title: str
    status: str
    url: str


class LinkTargetListResponse(BaseModel):
    items: list[LinkTargetResponse]


class DueRunResponse(_Out):
    checked_at: UtcDatetime
    published: list[dict[str, Any]]
    failed: list[dict[str, Any]]

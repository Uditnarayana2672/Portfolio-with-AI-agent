"""HTTP request/response schemas for project endpoints (presentation layer)."""
from __future__ import annotations

import datetime
import json
import uuid

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.application.dtos.project import ALLOWED_TEMPLATE_IDS, ALLOWED_VISIBILITY


# ── request shapes ─────────────────────────────────────────────────────────────


class SeoRequest(BaseModel):
    meta_title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
    canonical_url: str | None = None


class CreateProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Project title (non-empty).")
    slug: str | None = Field(
        None,
        description="URL slug. Auto-generated from title if omitted; `-2`/`-3` appended on collision.",
    )
    excerpt: str | None = Field(None, description="Short project summary.")
    template_id: str = Field(
        "narrative",
        description=f"Layout template. Allowed: {sorted(ALLOWED_TEMPLATE_IDS)}.",
    )
    tech_stack: list[str] = Field(default_factory=list, description="Technologies used.")
    github_url: str | None = Field(None, description="Link to the GitHub repository.")
    demo_url: str | None = Field(None, description="Link to the live demo.")
    status: str = Field(
        "draft",
        description="Must be `draft` on initial create. Publish via a dedicated endpoint.",
    )
    visibility: str = Field(
        "public",
        description=f"Audience visibility. Allowed: {sorted(ALLOWED_VISIBILITY)}.",
    )
    is_featured: bool = Field(False, description="Pin to the featured section.")
    seo: SeoRequest = Field(default_factory=SeoRequest, description="SEO / OG meta overrides.")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v

    @field_validator("template_id")
    @classmethod
    def template_id_allowed(cls, v: str) -> str:
        if v not in ALLOWED_TEMPLATE_IDS:
            raise ValueError(
                f"template_id {v!r} is not valid. Allowed: {sorted(ALLOWED_TEMPLATE_IDS)}"
            )
        return v

    @field_validator("visibility")
    @classmethod
    def visibility_allowed(cls, v: str) -> str:
        if v not in ALLOWED_VISIBILITY:
            raise ValueError(
                f"visibility {v!r} is not valid. Allowed: {sorted(ALLOWED_VISIBILITY)}"
            )
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_draft(cls, v: str) -> str:
        if v != "draft":
            raise ValueError(
                "status must be 'draft' on initial create; publish separately"
            )
        return v


_CONFIG_MAX_BYTES = 65_536  # 64 KB — guards against oversized JSONB payloads


class AddBlockRequest(BaseModel):
    block_type: str = Field(
        ...,
        description=(
            "One of the 13 supported block types: hero, text, image, gallery, "
            "video, code, timeline, stats, poll, quote, comparison, cta, form."
        ),
    )
    position: int = Field(
        ...,
        ge=0,
        description=(
            "Zero-based position in the page (0 = first). Values past the end "
            "are clamped to append; existing blocks at this position shift down."
        ),
    )
    config: dict = Field(
        ...,
        description="Type-specific config, validated against the schema for `block_type`.",
    )

    @field_validator("config")
    @classmethod
    def config_not_too_large(cls, v: dict) -> dict:
        if len(json.dumps(v, separators=(",", ":"))) > _CONFIG_MAX_BYTES:
            raise ValueError("config must not exceed 64 KB")
        return v


class UpdateProjectRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    excerpt: str | None = None
    thumbnail_url: str | None = None
    tech_stack: list[str] | None = None
    template_id: str | None = None
    github_url: str | None = None
    demo_url: str | None = None
    status: str | None = None
    visibility: str | None = None
    is_featured: bool | None = None
    seo: SeoRequest | None = None


# ── response shapes ────────────────────────────────────────────────────────────


class SeoResponse(BaseModel):
    meta_title: str | None
    meta_description: str | None
    og_image_url: str | None
    canonical_url: str | None


class BlockResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    block_type: str
    position: int
    config: dict
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CreateProjectResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    thumbnail_url: str | None
    tech_stack: list[str]
    template_id: str
    github_url: str | None
    demo_url: str | None
    status: str
    visibility: str
    is_featured: bool
    views: int
    seo: SeoResponse
    blocks: list = Field(default_factory=list, description="Content blocks — always empty on create.")
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @field_serializer("published_at")
    def _serialize_published_at(self, value: datetime.datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UpdateProjectResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    thumbnail_url: str | None
    tech_stack: list[str]
    template_id: str
    github_url: str | None
    demo_url: str | None
    status: str
    visibility: str
    is_featured: bool
    views: int
    seo: SeoResponse
    blocks: list[BlockResponse]
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    warnings: list[str] = Field(default_factory=list)

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @field_serializer("published_at")
    def _serialize_published_at(self, value: datetime.datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GetProjectResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    thumbnail_url: str | None
    tech_stack: list[str]
    template_id: str
    github_url: str | None
    demo_url: str | None
    status: str
    visibility: str
    is_featured: bool
    views: int
    seo: SeoResponse
    blocks: list[BlockResponse]
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @field_serializer("published_at")
    def _serialize_published_at(self, value: datetime.datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

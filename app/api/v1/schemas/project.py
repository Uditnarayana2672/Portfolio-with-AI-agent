"""HTTP request/response schemas for project endpoints (presentation layer)."""
from __future__ import annotations

import datetime
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


# ── response shapes ────────────────────────────────────────────────────────────


class SeoResponse(BaseModel):
    meta_title: str | None
    meta_description: str | None
    og_image_url: str | None
    canonical_url: str | None


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

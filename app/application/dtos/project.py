"""DTOs for project use cases (application layer).

Commands carry validated intent from the HTTP edge inward; Results carry
data back outward — no FastAPI or SQLAlchemy types here.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

ALLOWED_TEMPLATE_IDS: frozenset[str] = frozenset({
    "narrative",
    "gallery",
    "case-study",
    "minimal",
})

ALLOWED_VISIBILITY: frozenset[str] = frozenset({
    "public",
    "members_only",
    "unlisted",
})

ALLOWED_UPDATE_STATUS: frozenset[str] = frozenset({
    "draft",
    "published",
})


@dataclass(frozen=True)
class SeoInput:
    meta_title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
    canonical_url: str | None = None


@dataclass
class CreateProjectCommand:
    title: str
    author_id: uuid.UUID
    slug: str | None = None
    excerpt: str | None = None
    template_id: str = "narrative"
    tech_stack: list[str] = field(default_factory=list)
    github_url: str | None = None
    demo_url: str | None = None
    visibility: str = "public"
    is_featured: bool = False
    seo: SeoInput = field(default_factory=SeoInput)


@dataclass(frozen=True)
class CreateProjectResult:
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
    seo: dict
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


@dataclass(frozen=True)
class BlockResult:
    id: uuid.UUID
    project_id: uuid.UUID
    block_type: str
    position: int
    config: dict
    created_at: datetime.datetime
    updated_at: datetime.datetime


@dataclass
class UpdateProjectCommand:
    project_id: uuid.UUID
    requester_id: uuid.UUID
    fields: dict


@dataclass(frozen=True)
class UpdateProjectResult:
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
    seo: dict
    blocks: list[BlockResult]
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    warnings: list[str]


@dataclass(frozen=True)
class GetProjectResult:
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
    seo: dict
    blocks: list[BlockResult]
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

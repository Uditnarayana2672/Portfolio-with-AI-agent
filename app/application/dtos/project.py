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

SUPPORTED_BLOCK_TYPES: frozenset[str] = frozenset({
    "hero",
    "text",
    "image",
    "gallery",
    "video",
    "code",
    "timeline",
    "stats",
    "poll",
    "quote",
    "comparison",
    "cta",
    "form",
})

MAX_POLL_OPTIONS = 6
MIN_POLL_OPTIONS = 2
MAX_CODE_LENGTH = 50_000

# Cap on how many projects can be featured on the public homepage at once.
# Toggling a project to featured beyond this returns 409.
MAX_FEATURED_PROJECTS = 3


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
class AddBlockCommand:
    project_id: uuid.UUID
    requester_id: uuid.UUID
    block_type: str
    position: int
    config: dict


@dataclass
class UpdateBlockCommand:
    project_id: uuid.UUID
    block_id: uuid.UUID
    requester_id: uuid.UUID
    # None means "field omitted — leave unchanged". For config, an empty dict
    # ({}) is distinct from None: it is a provided-but-empty partial (no-op
    # merge), whereas None means the config key was absent from the request.
    position: int | None = None
    config: dict | None = None


@dataclass
class UpdateProjectCommand:
    project_id: uuid.UUID
    requester_id: uuid.UUID
    fields: dict


@dataclass
class ToggleFeatureCommand:
    project_id: uuid.UUID
    requester_id: uuid.UUID
    is_featured: bool


@dataclass(frozen=True)
class ToggleFeatureResult:
    id: uuid.UUID
    is_featured: bool


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

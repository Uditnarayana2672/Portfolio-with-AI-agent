"""Blog domain entities (core layer).

Framework-free representations of a blog post (the editor's working copy), its
revisions, categories, and the media it references. The ORM models in
infrastructure map to/from these.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class BlogPost:
    id: uuid.UUID
    title: str
    subtitle: str | None
    slug: str
    slug_locked: bool
    content: dict
    content_html: str
    content_text: str
    content_hash: str | None
    excerpt: str | None
    category_id: uuid.UUID | None
    tags: list[str]
    status: str              # 'draft' | 'review' | 'scheduled' | 'published' | 'archived'
    visibility: str
    allow_comments: bool
    seo: dict
    author_id: uuid.UUID
    cover_asset_id: uuid.UUID | None
    og_asset_id: uuid.UUID | None
    cover_image_url: str | None
    og_image_url: str | None
    word_count: int
    block_count: int
    read_time: int | None
    version: int
    published_revision_id: uuid.UUID | None
    scheduled_at: datetime.datetime | None
    published_at: datetime.datetime | None
    last_published_at: datetime.datetime | None
    schedule_error: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


@dataclass(frozen=True)
class BlogRevision:
    id: uuid.UUID
    post_id: uuid.UUID
    kind: str                # 'publish' | 'manual' | 'restore'
    label: str | None
    snapshot: dict
    content_html: str
    content_hash: str
    word_count: int
    created_by: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime.datetime


@dataclass(frozen=True)
class BlogCategory:
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    sort_order: int
    created_at: datetime.datetime
    post_count: int = 0
    published_count: int = 0


@dataclass(frozen=True)
class BlogMedia:
    """The slice of a media asset a post needs to reference and render it."""

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


@dataclass(frozen=True)
class LinkTarget:
    type: str                # 'blog' | 'project'
    id: str
    title: str
    status: str
    url: str


@dataclass(frozen=True)
class AuthorInfo:
    id: uuid.UUID
    name: str
    avatar_url: str | None = None

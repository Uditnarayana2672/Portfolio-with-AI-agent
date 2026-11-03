"""Blog editor DTOs (application layer).

Plain input/output data for the blog use cases, decoupled from the HTTP
request/response shapes in api/v1/schemas/blog.py.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

from app.application.interfaces.blog_content_renderer import TocEntry
from app.domain.blog.checklist import Checklist
from app.domain.entities.blog_post import AuthorInfo, BlogCategory, BlogMedia, BlogRevision

# Fields the editor may write. Anything else in a request is ignored.
WRITABLE_FIELDS = (
    "title", "subtitle", "slug", "slug_locked", "content", "excerpt",
    "cover_asset_id", "og_asset_id", "category_id", "tags", "allow_comments", "seo",
)

MEDIA_FOLDERS = {
    "cover": "blog/covers",
    "inline": "blog/inline",
    "gallery": "blog/inline",
    "video": "blog/videos",
    "og": "system/og-images",
}


@dataclass(frozen=True)
class BlogSettings:
    site_url: str = "https://uditnarayana.dev"
    blog_base_path: str = "/blog"
    timezone: str = "Asia/Kolkata"
    title_suffix: str = " · Udit N."
    author_display_name: str = "Udit N."
    schedule_min_lead_minutes: int = 5
    schedule_max_days_ahead: int = 365
    revisions_keep: int = 50
    words_per_minute: int = 230

    def public_url(self, slug: str) -> str:
        return f"{self.site_url.rstrip('/')}{self.blog_base_path}/{slug}"


@dataclass(frozen=True)
class PostStats:
    word_count: int
    reading_time_min: int
    block_count: int
    image_count: int


@dataclass(frozen=True)
class SeoEffective:
    meta_title: str
    meta_description: str
    canonical_url: str
    og_image_url: str | None


@dataclass(frozen=True)
class PostView:
    """Everything the editor shows for one post (API: PostDetail)."""

    id: uuid.UUID
    version: int
    title: str
    subtitle: str | None
    slug: str
    slug_locked: bool
    content: dict
    excerpt: str | None
    cover: BlogMedia | None
    og_image: BlogMedia | None
    category: BlogCategory | None
    tags: list[str]
    allow_comments: bool
    seo: dict
    seo_effective: SeoEffective
    status: str
    status_label: str
    scheduled_at: datetime.datetime | None
    published_at: datetime.datetime | None
    last_published_at: datetime.datetime | None
    has_unpublished_changes: bool
    public_url: str | None
    schedule_error: str | None
    stats: PostStats
    checklist: Checklist
    author: AuthorInfo | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


@dataclass(frozen=True)
class SaveWarning:
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class SaveResult:
    """The light autosave response (API: PostSaveResult)."""

    id: uuid.UUID
    version: int
    updated_at: datetime.datetime
    slug: str
    slug_adjusted: bool
    stats: PostStats
    has_unpublished_changes: bool
    checklist: Checklist
    warnings: list[SaveWarning] = field(default_factory=list)


@dataclass(frozen=True)
class SlugCheckResult:
    input: str
    slug: str
    available: bool
    reason: str | None
    suggested: str | None


@dataclass(frozen=True)
class RevisionView:
    revision: BlogRevision
    is_live: bool


@dataclass(frozen=True)
class RevisionPage:
    items: list[RevisionView]
    total: int
    page: int
    limit: int


@dataclass(frozen=True)
class PublicPost:
    """What a reader sees — the preview and the future public endpoint share it."""

    title: str
    subtitle: str | None
    slug: str
    url: str
    cover: dict | None
    category: dict | None
    tags: list[dict]
    author: dict
    published_at: datetime.datetime | None
    updated_at: datetime.datetime
    reading_time_min: int
    word_count: int
    toc: list[TocEntry]
    content_html: str
    head: dict


@dataclass(frozen=True)
class PreviewView:
    source: str
    post_id: uuid.UUID
    version: int
    status: str
    post: PublicPost
    search_preview: dict
    social_preview: dict
    checklist: Checklist
    generated_at: datetime.datetime


@dataclass(frozen=True)
class DueRunResult:
    checked_at: datetime.datetime
    published: list[dict]
    failed: list[dict]

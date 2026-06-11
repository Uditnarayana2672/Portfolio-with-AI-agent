"""Project domain entity (core layer).

Framework-free representation of a portfolio project. No SQLAlchemy, FastAPI,
or third-party types here — just plain Python. The ORM model in infrastructure
maps to/from this.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Project:
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    thumbnail_url: str | None
    tech_stack: list[str]
    template_id: str
    github_url: str | None
    demo_url: str | None
    status: str          # 'draft' | 'published' | 'archived'
    visibility: str      # 'public' | 'members_only' | 'unlisted'
    is_featured: bool
    views: int
    seo: dict
    author_id: uuid.UUID
    published_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

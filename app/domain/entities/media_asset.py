"""MediaAsset domain entity (core layer).

A framework-free representation of one stored media asset. No SQLAlchemy,
FastAPI, or Cloudinary types here — just plain Python. The ORM model in
infrastructure maps to/from this.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaAsset:
    id: uuid.UUID
    cloudinary_url: str | None
    public_id: str | None
    resource_type: str          # 'image' | 'video' | 'raw'
    format: str | None
    width: int | None
    height: int | None
    file_size: int | None       # bytes
    file_name: str | None
    folder: str
    alt_text: str | None
    source_type: str            # 'cloudinary' | 'youtube'
    external_id: str | None     # YouTube video id when source_type='youtube'
    thumbnail_url: str | None
    video_title: str | None
    video_duration_seconds: int | None
    file_hash: str | None       # SHA-256 of the binary; NULL for URL imports
    is_orphan: bool             # CDN asset gone but DB row remains
    uploaded_by: uuid.UUID | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

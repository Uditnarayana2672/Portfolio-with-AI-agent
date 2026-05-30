"""MediaAsset domain entity (core layer).

A framework-free representation of one stored media asset. No SQLAlchemy,
FastAPI, or Cloudinary types belong here — just plain Python. The ORM model in
infrastructure (app/infrastructure/persistence/orm/models.py :: MediaAssets)
maps to/from this entity.

TODO (implement manually):
  - Define a `MediaAsset` value object (a frozen @dataclass is a good fit).
  - Mirror the columns you need from the `MediaAssets` ORM model, e.g.:
        id, cloudinary_url, public_id, resource_type, format, width, height,
        file_size, file_name, folder, alt_text, source_type, external_id,
        thumbnail_url, video_title, video_duration_seconds, file_hash,
        is_orphan, uploaded_by, created_at, updated_at
  - Keep it dependency-free: no ORM/HTTP imports, only stdlib types
    (uuid.UUID, datetime.datetime, str | None, etc.).
"""
from __future__ import annotations

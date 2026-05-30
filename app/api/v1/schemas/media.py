"""HTTP request/response schemas for media endpoints (presentation layer).

Pydantic models that define the exact JSON shape the API emits. Kept separate
from the application DTOs so the wire contract can evolve independently.

TODO (implement manually):
  - Define `MediaAssetResponse` (pydantic BaseModel) with the per-asset fields
    the frontend needs. Use ConfigDict(from_attributes=True) so it can validate
    straight from a MediaAssetView. Serialize created_at / updated_at as UTC
    with a trailing "Z" (e.g. 2026-05-27T11:48:00Z) per the API contract.
  - Define `MediaListResponse`:
        assets: list[MediaAssetResponse]
        total: int
        page: int
        limit: int
        folder_stats: dict[str, int]
        type_stats: dict[str, int]
"""
from __future__ import annotations

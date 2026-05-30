"""SQLAlchemy implementation of MediaAssetRepository (infrastructure layer).

This is the ONLY media file allowed to know about SQL / SQLAlchemy. It adapts
the domain port to the `MediaAssets` ORM model and maps ORM rows back into
framework-free MediaAsset entities.

TODO (implement manually):
  - Define `SqlAlchemyMediaAssetRepository(MediaAssetRepository)` taking a
    SQLAlchemy `Session` in __init__.
  - list(...):
      * Build WHERE conditions from folder / resource_type / search
        (search = case-insensitive ILIKE across file_name, alt_text, public_id;
         resource_type must be cast to the ResourceType enum).
      * Get the total count for those conditions (ignoring offset/limit).
      * Select MediaAssets OUTER JOIN Users (to fetch the uploader's name),
        order by the chosen column (map sort_by -> ORM column) asc/desc,
        then offset/limit. Return a MediaListPage of MediaAssetListItem.
  - folder_stats(): GROUP BY folder COUNT(*) across the whole table, then add
    an "all" key = sum of the counts.
  - type_stats(): GROUP BY resource_type COUNT(*) across the whole table
    (remember to unwrap the enum to its .value for the dict key).
  - _to_entity(orm_row) -> MediaAsset: copy columns across.

Imports you'll likely need (left here as a hint, not active code):
    from sqlalchemy import asc, desc, func, or_, select
    from sqlalchemy.orm import Session
    from app.infrastructure.persistence.orm.models import MediaAssets, ResourceType, Users
"""
from __future__ import annotations

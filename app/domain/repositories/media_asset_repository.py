"""MediaAssetRepository port (domain layer).

The abstract contract the application layer depends on for querying media
assets. The concrete SQLAlchemy implementation lives in infrastructure
(app/infrastructure/persistence/repositories/media_asset_repository.py) and is
the only place that knows about SQL.

TODO (implement manually):
  - Define an abstract base class `MediaAssetRepository` (use abc.ABC) with the
    methods the ListMedia use case needs:
        * list(*, folder, resource_type, search, sort_by, order, offset, limit)
            -> a page of results + the total count matching the filters.
        * folder_stats() -> dict[str, int]  # count per folder across the WHOLE
            table (filters ignored), plus an "all" grand total.
        * type_stats()   -> dict[str, int]  # count per resource_type, whole table.
  - Define small result containers the methods return, e.g. a `MediaListPage`
    (items + total) and a `MediaAssetListItem` (a MediaAsset paired with its
    uploader's display name, since that name comes from a JOIN, not the entity).
  - Depend only on the MediaAsset entity — no ORM/HTTP imports here.
"""
from __future__ import annotations

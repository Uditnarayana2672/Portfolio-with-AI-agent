"""ListMedia use case (application layer).

Orchestrates one business operation: list media assets with filtering, search,
sorting, and pagination. It holds NO SQL and NO HTTP/framework imports — it
talks to the repository through the domain port and returns DTOs.

TODO (implement manually):
  - Define a `ListMedia` class that takes a MediaAssetRepository in __init__
    (constructor injection — the provider wires the concrete repo in).
  - Implement `execute(query: ListMediaQuery) -> ListMediaResult`:
      1. Validate the enumerated params (sort_by, order, resource_type) against
         the VALID_* tuples; raise domain ValidationError -> the endpoint maps
         this to HTTP 400 INVALID_QUERY_PARAM.
      2. Normalise pagination: clamp page to >= 1 and limit to 1..MAX_LIMIT
         (spec: clamp, do not reject), then compute offset = (page - 1) * limit.
      3. Treat an empty/whitespace `search` as no search; empty folder as None.
      4. Call repo.list(...) for the page, then repo.folder_stats() and
         repo.type_stats() for the GLOBAL stats (filters ignored, so the
         sidebar/pills stay populated even on an empty filtered result).
      5. Map domain entities -> MediaAssetView (set cdn_status = "missing" if
         is_orphan else "ok") and return a ListMediaResult.
  - Reuse app.domain.exceptions.ValidationError (kept as scaffolding).
"""
from __future__ import annotations

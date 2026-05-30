"""DTOs for media use cases (application layer).

Plain dataclasses decoupled from both the ORM and the HTTP schemas. They are
the use case's input/output shapes.

TODO (implement manually):
  - Define the allowed query values + pagination bounds as constants (the single
    source of truth the use case validates against):
        VALID_SORT_BY = ("created_at", "file_size", "file_name")
        VALID_ORDER = ("asc", "desc")
        VALID_RESOURCE_TYPES = ("image", "video", "raw")
        DEFAULT_LIMIT = 30
        MAX_LIMIT = 100
  - Define `ListMediaQuery`  : the raw, unvalidated input from the HTTP layer
        (folder, resource_type, search, page, limit, sort_by, order).
  - Define `MediaAssetView`  : one asset as returned by the list endpoint
        (includes derived fields like cdn_status and the joined uploaded_by_name).
  - Define `ListMediaResult` : assets + total + page + limit + folder_stats +
        type_stats.
  - Keep these framework-free (stdlib dataclasses only).
"""
from __future__ import annotations

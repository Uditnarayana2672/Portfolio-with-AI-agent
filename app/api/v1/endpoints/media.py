"""Admin media management endpoints (presentation layer).

Thin controllers only: parse the request, call the use case, translate domain
errors into HTTP responses, serialize the result. NO business logic here.

TODO (implement manually):
  - Create `router = APIRouter(prefix="/admin/media", tags=["media"])`.
  - Implement GET "" -> response_model=MediaListResponse:
        Query params (all optional unless noted):
            folder: str | None
            resource_type: str | None    # image | video | raw
            search: str | None
            page: int = 1            (ge=1)
            limit: int = DEFAULT_LIMIT (ge=1; NO upper bound here — the use case
                                        clamps to MAX_LIMIT; spec says clamp, not reject)
            sort_by: str = "created_at"  # created_at | file_size | file_name
            order: str = "desc"          # asc | desc
        Guard with `_admin: Users = Depends(get_current_admin)` (admin-only).
        Inject the use case with `Depends(get_list_media)`.
        Build a ListMediaQuery, call use_case.execute(query); on ValidationError
        raise HTTPException(400, {"code": "INVALID_QUERY_PARAM", "message": ...}).
        Map ListMediaResult -> MediaListResponse and return it.

  - Once implemented, re-wire this router in app/api/v1/router.py
    (the include_router line for media is commented out there).
"""
from __future__ import annotations

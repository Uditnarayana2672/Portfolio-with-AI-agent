"""Admin media management endpoints (presentation layer).

Thin controllers: parse the request, call the use case, translate domain
errors to HTTP, serialize the result. No business logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_list_media
from app.api.v1.schemas.media import MediaAssetResponse, MediaListResponse
from app.application.dtos.media import DEFAULT_LIMIT, ListMediaQuery
from app.application.use_cases.media.list_media import ListMedia
from app.domain.exceptions import ValidationError
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin/media", tags=["media"])


@router.get("", response_model=MediaListResponse)
def list_media(
    folder: str | None = Query(default=None),
    resource_type: str | None = Query(default=None, description="image | video | raw"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    # No upper bound here — the use case clamps limit to 100 (spec: clamp, not reject).
    limit: int = Query(default=DEFAULT_LIMIT, ge=1),
    sort_by: str = Query(default="created_at", description="created_at | file_size | file_name"),
    order: str = Query(default="desc", description="asc | desc"),
    _admin: Users = Depends(get_current_admin),
    use_case: ListMedia = Depends(get_list_media),
) -> MediaListResponse:
    """List media assets with filtering, search, sorting, and pagination."""
    query = ListMediaQuery(
        folder=folder,
        resource_type=resource_type,
        search=search,
        page=page,
        limit=limit,
        sort_by=sort_by,
        order=order,
    )
    try:
        result = use_case.execute(query)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_QUERY_PARAM", "message": str(exc)},
        ) from exc

    return MediaListResponse(
        assets=[MediaAssetResponse.model_validate(a) for a in result.assets],
        total=result.total,
        page=result.page,
        limit=result.limit,
        folder_stats=result.folder_stats,
        type_stats=result.type_stats,
    )

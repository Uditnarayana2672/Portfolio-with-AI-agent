"""Admin media management endpoints (presentation layer).

Thin controllers: parse the request, call the use case, translate domain
errors to HTTP, serialize the result. No business logic here.
"""
from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import (
    get_import_url_media,
    get_list_media,
    get_media_asset,
    get_media_stats,
    get_upload_media,
)
from app.api.v1.schemas.media import (
    CleanupStatsResponse,
    ImportUrlRequest,
    MediaAssetDetailResponse,
    MediaAssetResponse,
    MediaListResponse,
    MediaStatsResponse,
    StorageStatsResponse,
    UploadedAssetResponse,
    UploadMediaResponse,
)
from app.application.dtos.media import (
    DEFAULT_LIMIT,
    ImportUrlCommand,
    ListMediaQuery,
    UploadMediaCommand,
)
from app.application.dtos.media import UploadMediaResult
from app.application.use_cases.media.get_media_asset import GetMediaAsset
from app.application.use_cases.media.get_media_stats import GetMediaStats
from app.application.use_cases.media.import_url_media import ImportUrlMedia
from app.application.use_cases.media.list_media import ListMedia
from app.application.use_cases.media.upload_media import UploadMedia
from app.domain.exceptions import (
    BlockedUrlError,
    FileTooLargeError,
    InvalidUrlError,
    NotFoundError,
    StorageUploadError,
    UnsupportedFileTypeError,
    UrlFetchError,
    ValidationError,
)
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


@router.get("/stats", response_model=MediaStatsResponse)
def media_stats(
    _admin: Users = Depends(get_current_admin),
    use_case: GetMediaStats = Depends(get_media_stats),
) -> MediaStatsResponse:
    """Top stat strip (5 ministat cards) + the Cloudinary storage banner."""
    result = use_case.execute()

    last_cleanup = (
        CleanupStatsResponse(
            ran_at=result.last_cleanup.ran_at,
            freed_bytes=result.last_cleanup.freed_bytes,
            freed_human=result.last_cleanup.freed_human,
            orphans_removed=result.last_cleanup.orphans_removed,
        )
        if result.last_cleanup is not None
        else None
    )

    return MediaStatsResponse(
        total_assets=result.total_assets,
        added_today=result.added_today,
        counts=result.counts,
        storage=StorageStatsResponse(
            used_bytes=result.storage.used_bytes,
            quota_bytes=result.storage.quota_bytes,
            used_human=result.storage.used_human,
            quota_human=result.storage.quota_human,
            percent_used=result.storage.percent_used,
            plan=result.storage.plan,
        ),
        last_cleanup=last_cleanup,
    )


@router.post(
    "/upload",
    response_model=UploadMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    file: UploadFile = File(...),
    folder: str = Form(...),
    resource_type: str | None = Form(default=None, description="image | video | raw"),
    file_name: str | None = Form(default=None, description="display-name override"),
    alt_text: str | None = Form(default=None),
    admin: Users = Depends(get_current_admin),
    use_case: UploadMedia = Depends(get_upload_media),
) -> JSONResponse:
    """Upload a media file (multipart). Returns 201 for a new asset, or 200 when
    an identical file (by SHA-256) already exists (`duplicate: true`)."""
    content = await file.read()
    command = UploadMediaCommand(
        content=content,
        original_filename=file.filename or "",
        folder=folder,
        uploaded_by=admin.id,
        resource_type=resource_type,
        file_name=file_name,
        alt_text=alt_text,
    )

    try:
        result = use_case.execute(command)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"got": exc.got, "allowed": exc.allowed},
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"max_bytes": exc.max_bytes, "limit": exc.limit},
        ) from exc
    except StorageUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"attempts": exc.attempts, "request_id": exc.request_id},
        ) from exc

    # Build the envelope explicitly so the `asset` object keeps its null fields
    # (e.g. alt_text: null) while the top-level `renamed`/`rename_note` keys are
    # present only when meaningful — matching the contract per case:
    #   duplicate → {duplicate, asset}
    #   new       → {duplicate, asset, renamed}        (+ rename_note if renamed)
    payload: dict = {
        "duplicate": result.duplicate,
        "asset": UploadedAssetResponse.model_validate(result.asset).model_dump(
            mode="json"
        ),
    }
    if not result.duplicate:
        payload["renamed"] = result.renamed
        if result.rename_note is not None:
            payload["rename_note"] = result.rename_note

    status_code = status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
    return JSONResponse(status_code=status_code, content=payload)


def _asset_payload(result: UploadMediaResult) -> dict:
    """Serialize the asset to the §3.3 shape, adding the YouTube-only fields
    (source_type/external_id/thumbnail_url/video_*) for registered videos."""
    asset = result.asset
    body = UploadedAssetResponse.model_validate(asset).model_dump(mode="json")
    if asset.source_type == "youtube":
        body["source_type"] = asset.source_type
        body["external_id"] = asset.external_id
        body["thumbnail_url"] = asset.thumbnail_url
        body["video_title"] = asset.video_title
        body["video_duration_seconds"] = asset.video_duration_seconds
    return body


@router.post(
    "/import-url",
    response_model=UploadMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_url(
    body: ImportUrlRequest,
    admin: Users = Depends(get_current_admin),
    use_case: ImportUrlMedia = Depends(get_import_url_media),
) -> JSONResponse:
    """Import an asset from a remote URL (server-side fetch with SSRF guards), or
    register a YouTube link. 201 for a new asset; 200 when it already exists."""
    command = ImportUrlCommand(
        url=body.url,
        folder=body.folder,
        uploaded_by=admin.id,
        alt_text=body.alt_text,
    )

    try:
        result = use_case.execute(command)
    except InvalidUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_URL", "message": str(exc)},
        ) from exc
    except BlockedUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BLOCKED_URL", "message": str(exc)},
        ) from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"got": exc.got, "allowed": exc.allowed},
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"max_bytes": exc.max_bytes, "limit": exc.limit},
        ) from exc
    except UrlFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "URL_FETCH_FAILED", "message": str(exc)},
        ) from exc
    except StorageUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"attempts": exc.attempts, "request_id": exc.request_id},
        ) from exc

    payload: dict = {"duplicate": result.duplicate, "asset": _asset_payload(result)}
    if not result.duplicate:
        payload["renamed"] = result.renamed
        if result.rename_note is not None:
            payload["rename_note"] = result.rename_note

    status_code = status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
    return JSONResponse(status_code=status_code, content=payload)


# Declared AFTER the static routes (/stats, /upload, /import-url) and typed as a
# UUID so it can never shadow them.
@router.get("/{asset_id}", response_model=MediaAssetDetailResponse)
def get_media_asset_detail(
    asset_id: uuid.UUID,
    _admin: Users = Depends(get_current_admin),
    use_case: GetMediaAsset = Depends(get_media_asset),
) -> MediaAssetDetailResponse:
    """Full asset object (the §3.1 shape) plus a convenience `usage_count`."""
    try:
        detail = use_case.execute(asset_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEDIA_NOT_FOUND", "message": str(exc)},
        ) from exc

    base = MediaAssetResponse.model_validate(detail.asset)
    return MediaAssetDetailResponse(**base.model_dump(), usage_count=detail.usage_count)

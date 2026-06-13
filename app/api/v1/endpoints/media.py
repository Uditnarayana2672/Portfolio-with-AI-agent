"""Admin media management endpoints (presentation layer).

Thin controllers: parse the request, call the use case, translate domain
errors to HTTP, serialize the result. No business logic here.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import (
    get_bulk_delete_media,
    get_bulk_update_media,
    get_delete_media,
    get_import_url_media,
    get_list_media,
    get_media_asset,
    get_media_stats,
    get_media_usage,
    get_update_media,
    get_upload_media,
)
from app.api.v1.schemas.media import (
    BulkDeleteMediaRequest,
    BulkDeleteMediaResponse,
    BulkUpdateMediaRequest,
    BulkUpdateMediaResponse,
    CleanupStatsResponse,
    ImportUrlRequest,
    MediaAssetDetailResponse,
    MediaAssetResponse,
    MediaListResponse,
    MediaStatsResponse,
    MediaUsageResponse,
    StorageStatsResponse,
    UpdateMediaRequest,
    UpdateMediaResponse,
    UploadedAssetResponse,
    UploadMediaApiResponse,
    UploadMediaResponse,
    UsageReferenceResponse,
)
from app.application.dtos.media import (
    BulkDeleteMediaCommand,
    BulkUpdateMediaCommand,
    DEFAULT_LIMIT,
    IMAGE_MAX_BYTES,
    ImportUrlCommand,
    ListMediaQuery,
    UpdateMediaCommand,
    UploadMediaCommand,
    UploadMediaResult,
)
from app.application.use_cases.media.bulk_delete_media import BulkDeleteMedia
from app.application.use_cases.media.bulk_update_media import BulkUpdateMedia
from app.application.use_cases.media.get_media_asset import GetMediaAsset
from app.application.use_cases.media.get_media_stats import GetMediaStats
from app.application.use_cases.media.get_media_usage import GetMediaUsage
from app.application.use_cases.media.import_url_media import ImportUrlMedia
from app.application.use_cases.media.delete_media import DeleteMedia
from app.application.use_cases.media.list_media import ListMedia
from app.application.use_cases.media.update_media import UpdateMedia
from app.application.use_cases.media.upload_media import UploadMedia
from app.application.interfaces.image_storage import StorageError
from app.domain.exceptions import (
    BlockedUrlError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFolderError,
    InvalidUrlError,
    MediaInUseError,
    NotFoundError,
    ResourceTypeMismatchError,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    return MediaListResponse(
        assets=[MediaAssetResponse.model_validate(a) for a in result.assets],
        total=result.total,
        page=result.page,
        limit=result.limit,
        total_pages=result.total_pages,
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
    response_model=UploadMediaApiResponse,
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
    """Upload a media file (multipart/form-data).

    Returns 201 with a flat asset object plus a ``warnings`` list.
    The ``warnings`` list is non-empty only when the upload succeeded with
    caveats (e.g. OG image with wrong dimensions).
    """
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
    except EmptyFileError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "EMPTY_FILE", "message": "Uploaded file is empty"},
        )
    except InvalidFolderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_FOLDER", "message": str(exc)},
        ) from exc
    except ResourceTypeMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "RESOURCE_TYPE_MISMATCH", "message": str(exc)},
        ) from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": "UNSUPPORTED_FILE_TYPE",
                "message": f"File type .{exc.got} is not allowed",
                "detail": {"allowed": exc.allowed},
            },
        ) from exc
    except FileTooLargeError as exc:
        resource_label = "Video" if exc.max_bytes > IMAGE_MAX_BYTES else "Image"
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": f"{resource_label} files cannot exceed {exc.limit}",
                "detail": {"max_bytes": exc.max_bytes},
            },
        ) from exc
    except StorageUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "CLOUDINARY_UPLOAD_FAILED",
                "message": f"Upload to Cloudinary failed after {exc.attempts} attempts",
            },
        ) from exc

    # Flat response matching the API 15 spec: all asset fields at the top level
    # plus a warnings list (non-empty only for OG images with wrong dimensions).
    payload = {
        **UploadedAssetResponse.model_validate(result.asset).model_dump(mode="json"),
        "warnings": result.warnings,
    }
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)


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


@router.post("/bulk-delete", response_model=BulkDeleteMediaResponse)
def bulk_delete_media_assets(
    body: BulkDeleteMediaRequest,
    admin: Users = Depends(get_current_admin),
    use_case: BulkDeleteMedia = Depends(get_bulk_delete_media),
) -> BulkDeleteMediaResponse:
    """Delete selected assets and report expected per-item skips."""
    try:
        result = use_case.execute(
            BulkDeleteMediaCommand(
                asset_ids=body.ids,
                force=body.force,
                performed_by=admin.id,
            )
        )
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "STORAGE_ERROR",
                "message": str(exc),
                "request_id": exc.request_id,
            },
        ) from exc

    return BulkDeleteMediaResponse.model_validate(result, from_attributes=True)


@router.post("/bulk-update", response_model=BulkUpdateMediaResponse)
def bulk_update_media_assets(
    body: BulkUpdateMediaRequest,
    _admin: Users = Depends(get_current_admin),
    use_case: BulkUpdateMedia = Depends(get_bulk_update_media),
) -> BulkUpdateMediaResponse:
    """Move selected assets and/or apply shared alt text."""
    updates = body.model_dump(exclude={"ids"}, exclude_unset=True)
    try:
        result = use_case.execute(
            BulkUpdateMediaCommand(asset_ids=body.ids, **updates)
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEDIA_NOT_FOUND", "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        code = "INVALID_FOLDER" if "folder" in body.model_fields_set else "INVALID_BULK_UPDATE"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": str(exc)},
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "STORAGE_ERROR",
                "message": str(exc),
                "request_id": exc.request_id,
            },
        ) from exc

    return BulkUpdateMediaResponse.model_validate(result, from_attributes=True)


# Declared AFTER the static routes (/stats, /upload, /import-url, /bulk-delete,
# /bulk-update) and typed as a UUID so it can never shadow them.
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


@router.patch("/{asset_id}", response_model=UpdateMediaResponse)
def update_media_asset(
    asset_id: uuid.UUID,
    body: UpdateMediaRequest,
    _admin: Users = Depends(get_current_admin),
    use_case: UpdateMedia = Depends(get_update_media),
) -> JSONResponse:
    """Edit alt text, rename the file, and/or move it to another folder. All
    fields optional — only what's sent is changed. Renaming file_name/folder
    renames the Cloudinary public_id (collision → numeric suffix) and returns
    the fresh cloudinary_url."""
    # exclude_unset → only the keys the client actually sent, so the use case
    # can tell "not provided" apart from an explicit null (e.g. clearing alt_text).
    command = UpdateMediaCommand(asset_id=asset_id, **body.model_dump(exclude_unset=True))

    try:
        result = use_case.execute(command)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEDIA_NOT_FOUND", "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FOLDER", "message": str(exc)},
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "STORAGE_ERROR", "message": str(exc), "request_id": exc.request_id},
        ) from exc

    # Build the envelope explicitly so the `asset` object keeps its null fields
    # (e.g. alt_text: null) while rename_note appears only when a collision
    # actually forced a suffix — matching the §3.7 contract.
    payload: dict = {
        "asset": MediaAssetResponse.model_validate(result.asset).model_dump(mode="json"),
        "renamed": result.renamed,
    }
    if result.rename_note is not None:
        payload["rename_note"] = result.rename_note

    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)


def _run_delete(action: Callable[[], object]) -> Response:
    try:
        action()
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEDIA_NOT_FOUND", "message": str(exc)},
        ) from exc
    except MediaInUseError as exc:
        # The §3.8 contract uses a flat {error, message, detail} envelope here
        # (not the usual {detail:{code,message}}), so return it verbatim.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "MEDIA_IN_USE",
                "message": str(exc),
                "detail": {
                    "usage_count": exc.usage_count,
                    "references": [
                        UsageReferenceResponse.model_validate(
                            ref, from_attributes=True
                        ).model_dump(mode="json")
                        for ref in exc.references
                    ],
                },
            },
        )
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "STORAGE_ERROR",
                "message": str(exc),
                "request_id": exc.request_id,
            },
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/by-id/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_asset_by_id(
    asset_id: uuid.UUID,
    force: bool = Query(default=False, description="bypass the in-use guard"),
    admin: Users = Depends(get_current_admin),
    use_case: DeleteMedia = Depends(get_delete_media),
) -> Response:
    """Delete any asset by UUID, including external assets such as YouTube
    videos that have no Cloudinary public_id."""
    return _run_delete(
        lambda: use_case.execute_by_id(asset_id, force=force, performed_by=admin.id)
    )


# public_id contains slashes (folder/stem) and arrives URL-encoded; the :path
# converter lets the single param capture the whole decoded id. Keep static
# DELETE routes above this greedy match.
@router.delete("/{public_id:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_asset(
    public_id: str,
    force: bool = Query(default=False, description="bypass the in-use guard"),
    admin: Users = Depends(get_current_admin),
    use_case: DeleteMedia = Depends(get_delete_media),
) -> Response:
    """Delete one Cloudinary asset by public_id. Refused with 409 while the
    asset is still referenced unless `?force=true`."""
    return _run_delete(
        lambda: use_case.execute(public_id, force=force, performed_by=admin.id)
    )


@router.get("/{asset_id}/usage", response_model=MediaUsageResponse)
def get_media_usage_references(
    asset_id: uuid.UUID,
    _admin: Users = Depends(get_current_admin),
    use_case: GetMediaUsage = Depends(get_media_usage),
) -> MediaUsageResponse:
    """Where this asset is used ("Used in N places") — for the drawer and the
    delete-confirm modal. Matches the asset's public_id across project
    thumbnails/blocks and blog cover/og/content."""
    try:
        result = use_case.execute(asset_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEDIA_NOT_FOUND", "message": str(exc)},
        ) from exc

    return MediaUsageResponse.model_validate(result, from_attributes=True)

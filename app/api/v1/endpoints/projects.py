"""Admin project endpoints — create draft project (presentation layer).

Thin controller: parse the request, call the use case, translate domain errors
to HTTP, serialize the result. No business logic here.
"""
from __future__ import annotations

import uuid

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError as PydanticValidationError

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_add_block, get_check_slug_availability, get_create_project, get_delete_block, get_delete_project, get_duplicate_project, get_get_project, get_reorder_blocks, get_toggle_feature, get_update_block, get_update_project
from app.api.v1.schemas.block_config import BLOCK_CONFIG_MODELS
from app.api.v1.schemas.project import (
    AddBlockRequest,
    BlockResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    DuplicateProjectRequest,
    DuplicateProjectResponse,
    GetProjectResponse,
    ReorderBlocksRequest,
    ReorderBlocksResponse,
    SeoResponse,
    SlugCheckResponse,
    ToggleFeatureRequest,
    ToggleFeatureResponse,
    UpdateBlockRequest,
    UpdateProjectRequest,
    UpdateProjectResponse,
)
from app.application.dtos.project import MAX_FEATURED_PROJECTS, AddBlockCommand, CheckSlugCommand, CreateProjectCommand, DuplicateProjectCommand, ReorderBlocksCommand, SeoInput, ToggleFeatureCommand, UpdateBlockCommand, UpdateProjectCommand
from app.application.use_cases.projects.add_block import AddBlock
from app.application.use_cases.projects.check_slug_availability import CheckSlugAvailability
from app.application.use_cases.projects.create_project import CreateProject
from app.application.use_cases.projects.duplicate_project import DuplicateProject
from app.application.use_cases.projects.delete_block import DeleteBlock
from app.application.use_cases.projects.delete_project import DeleteProject
from app.application.use_cases.projects.get_project import GetProject
from app.application.use_cases.projects.reorder_blocks import ReorderBlocks
from app.application.use_cases.projects.toggle_feature import ToggleFeature
from app.application.use_cases.projects.update_block import UpdateBlock
from app.application.use_cases.projects.update_project import UpdateProject
from app.domain.exceptions import BlockReorderError, CodeTooLongError, ConflictError, NotFoundError, PermissionError, SlugTakenError, ValidationError
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin/projects", tags=["Projects"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateProjectResponse,
    summary="Create a draft project",
    description=(
        "Create a new portfolio project in **draft** status. "
        "The `slug` is auto-generated from the title when omitted, "
        "with a numeric suffix (`-2`, `-3`, …) appended automatically on collision. "
        "A project created here always starts as `draft`; "
        "publishing must be done via a separate endpoint."
    ),
)
def create_project(
    body: CreateProjectRequest,
    current_admin: Users = Depends(get_current_admin),
    use_case: CreateProject = Depends(get_create_project),
) -> CreateProjectResponse:
    cmd = CreateProjectCommand(
        title=body.title,
        author_id=current_admin.id,
        slug=body.slug,
        excerpt=body.excerpt,
        template_id=body.template_id,
        tech_stack=list(body.tech_stack),
        github_url=body.github_url,
        demo_url=body.demo_url,
        visibility=body.visibility,
        is_featured=body.is_featured,
        seo=SeoInput(
            meta_title=body.seo.meta_title,
            meta_description=body.seo.meta_description,
            og_image_url=body.seo.og_image_url,
            canonical_url=body.seo.canonical_url,
        ),
    )

    try:
        result = use_case.execute(cmd)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return CreateProjectResponse(
        id=result.id,
        title=result.title,
        slug=result.slug,
        excerpt=result.excerpt,
        thumbnail_url=result.thumbnail_url,
        tech_stack=result.tech_stack,
        template_id=result.template_id,
        github_url=result.github_url,
        demo_url=result.demo_url,
        status=result.status,
        visibility=result.visibility,
        is_featured=result.is_featured,
        views=result.views,
        seo=SeoResponse(
            meta_title=result.seo.get("meta_title"),
            meta_description=result.seo.get("meta_description"),
            og_image_url=result.seo.get("og_image_url"),
            canonical_url=result.seo.get("canonical_url"),
        ),
        blocks=[],
        author_id=result.author_id,
        published_at=result.published_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post(
    "/{project_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    response_model=DuplicateProjectResponse,
    summary="Duplicate a project",
    description=(
        "Create a complete copy of an existing project, including all its content blocks. "
        "The duplicate is always created as a **draft** with `views` reset to `0`, "
        "`is_featured` set to `false`, `published_at` set to `null`, and "
        "`seo.canonical_url` cleared to avoid duplicate canonical conflicts. "
        "If `new_title` is omitted the title defaults to `'{original} (copy)'`. "
        "If `new_slug` is omitted it is auto-generated from the new title with a "
        "numeric suffix on collision. "
        "If `new_slug` is provided but already taken, the request fails with `409 SLUG_TAKEN`."
    ),
)
def duplicate_project(
    project_id: uuid.UUID,
    body: DuplicateProjectRequest,
    current_admin: Users = Depends(get_current_admin),
    use_case: DuplicateProject = Depends(get_duplicate_project),
) -> DuplicateProjectResponse:
    cmd = DuplicateProjectCommand(
        source_id=project_id,
        author_id=current_admin.id,
        new_title=body.new_title,
        new_slug=body.new_slug,
    )

    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except SlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SLUG_TAKEN",
                "message": str(exc),
                "detail": {"suggested": exc.suggested},
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    p = result.new_project
    return DuplicateProjectResponse(
        original_id=result.original_id,
        new_project=GetProjectResponse(
            id=p.id,
            title=p.title,
            slug=p.slug,
            excerpt=p.excerpt,
            thumbnail_url=p.thumbnail_url,
            tech_stack=p.tech_stack,
            template_id=p.template_id,
            github_url=p.github_url,
            demo_url=p.demo_url,
            status=p.status,
            visibility=p.visibility,
            is_featured=p.is_featured,
            views=p.views,
            seo=SeoResponse(
                meta_title=p.seo.get("meta_title"),
                meta_description=p.seo.get("meta_description"),
                og_image_url=p.seo.get("og_image_url"),
                canonical_url=p.seo.get("canonical_url"),
            ),
            blocks=[
                BlockResponse(
                    id=b.id,
                    project_id=b.project_id,
                    block_type=b.block_type,
                    position=b.position,
                    config=b.config,
                    created_at=b.created_at,
                    updated_at=b.updated_at,
                )
                for b in p.blocks
            ],
            author_id=p.author_id,
            published_at=p.published_at,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ),
    )


@router.post(
    "/{project_id}/blocks",
    status_code=status.HTTP_201_CREATED,
    response_model=BlockResponse,
    summary="Add a block to a project",
    description=(
        "Add a new content block to a project. There are 13 supported block "
        "types (hero, text, image, gallery, video, code, timeline, stats, poll, "
        "quote, comparison, cta, form); the `config` object is validated against "
        "the schema for the given `block_type`. `position` controls placement "
        "(0 = first): existing blocks at or after it shift down by one, and a "
        "position past the end is clamped to append."
    ),
)
def add_block(
    project_id: uuid.UUID,
    body: AddBlockRequest,
    current_admin: Users = Depends(get_current_admin),
    use_case: AddBlock = Depends(get_add_block),
) -> BlockResponse:
    config_model = BLOCK_CONFIG_MODELS.get(body.block_type)
    if config_model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "message": f"block_type '{body.block_type}' is not supported",
            },
        )

    try:
        config = config_model.model_validate(body.config)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "message": f"{body.block_type}.{loc}: {first['msg']}" if loc
                else f"{body.block_type} config: {first['msg']}",
            },
        ) from exc

    cmd = AddBlockCommand(
        project_id=project_id,
        requester_id=current_admin.id,
        block_type=body.block_type,
        position=body.position,
        config=config.model_dump(),
    )

    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc
    except CodeTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "CODE_TOO_LONG", "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    return BlockResponse(
        id=result.id,
        project_id=result.project_id,
        block_type=result.block_type,
        position=result.position,
        config=result.config,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.patch(
    "/{project_id}/feature",
    status_code=status.HTTP_200_OK,
    response_model=ToggleFeatureResponse,
    summary="Toggle a project's featured flag",
    description=(
        "Mark a project as featured (or not) on the public homepage. "
        "A dedicated endpoint so the toggle can fire from a list view without "
        "the full project payload. `is_featured` must be a real JSON boolean — "
        "the string `\"true\"` is rejected. Setting the flag to a value it "
        "already holds is a 200 no-op. At most "
        f"{MAX_FEATURED_PROJECTS} projects may be featured at once; "
        "exceeding that returns 409."
    ),
)
def toggle_feature(
    project_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    current_admin: Users = Depends(get_current_admin),
    use_case: ToggleFeature = Depends(get_toggle_feature),
) -> ToggleFeatureResponse:
    # Parse manually (rather than binding ToggleFeatureRequest directly) so the
    # error shape matches the API contract: {"error": ..., "message": ...}.
    try:
        body = ToggleFeatureRequest.model_validate(payload)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        message = (
            "is_featured is required"
            if first.get("type") == "missing"
            else "is_featured must be a boolean"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": message},
        ) from exc

    cmd = ToggleFeatureCommand(
        project_id=project_id,
        requester_id=current_admin.id,
        is_featured=body.is_featured,
    )

    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": "Project not found"},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "FEATURED_LIMIT_REACHED", "message": str(exc)},
        ) from exc

    return ToggleFeatureResponse(id=result.id, is_featured=result.is_featured)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a project",
    description=(
        "Permanently delete a project and all its content blocks (cascade). "
        "Media assets referenced by this project are **not** deleted. "
        "This action is irreversible."
    ),
)
def delete_project(
    project_id: uuid.UUID,
    current_admin: Users = Depends(get_current_admin),
    use_case: DeleteProject = Depends(get_delete_project),
) -> None:
    try:
        use_case.execute(project_id, current_admin.id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc


@router.put(
    "/{project_id}",
    status_code=status.HTTP_200_OK,
    response_model=UpdateProjectResponse,
    summary="Update an existing project",
    description=(
        "Partially update a project — send only the fields that changed. "
        "An empty body `{}` is a valid no-op (auto-save fires even when nothing changed). "
        "Setting `status=published` automatically stamps `published_at`; "
        "setting it back to `draft` preserves the original `published_at`. "
        "SEO keys are merged: unset keys in the request are left untouched."
    ),
)
def update_project(
    project_id: uuid.UUID,
    body: UpdateProjectRequest,
    current_admin: Users = Depends(get_current_admin),
    use_case: UpdateProject = Depends(get_update_project),
) -> UpdateProjectResponse:
    provided: dict = {}
    for field_name in body.model_fields_set:
        if field_name == "seo":
            if body.seo is not None:
                provided["seo"] = body.seo.model_dump(exclude_unset=True)
        else:
            provided[field_name] = getattr(body, field_name)

    cmd = UpdateProjectCommand(
        project_id=project_id,
        requester_id=current_admin.id,
        fields=provided,
    )

    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc
    except SlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SLUG_TAKEN",
                "message": str(exc),
                "detail": {"suggested": exc.suggested},
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    return UpdateProjectResponse(
        id=result.id,
        title=result.title,
        slug=result.slug,
        excerpt=result.excerpt,
        thumbnail_url=result.thumbnail_url,
        tech_stack=result.tech_stack,
        template_id=result.template_id,
        github_url=result.github_url,
        demo_url=result.demo_url,
        status=result.status,
        visibility=result.visibility,
        is_featured=result.is_featured,
        views=result.views,
        seo=SeoResponse(
            meta_title=result.seo.get("meta_title"),
            meta_description=result.seo.get("meta_description"),
            og_image_url=result.seo.get("og_image_url"),
            canonical_url=result.seo.get("canonical_url"),
        ),
        blocks=[
            BlockResponse(
                id=b.id,
                project_id=b.project_id,
                block_type=b.block_type,
                position=b.position,
                config=b.config,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in result.blocks
        ],
        author_id=result.author_id,
        published_at=result.published_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
        warnings=result.warnings,
    )


# IMPORTANT: this route MUST be registered before /{project_id}/blocks/{block_id}.
# FastAPI matches routes in declaration order; registering /reorder after /{block_id}
# causes FastAPI to try to parse the literal string "reorder" as a UUID and return 422.
@router.patch(
    "/{project_id}/blocks/reorder",
    status_code=status.HTTP_200_OK,
    response_model=ReorderBlocksResponse,
    summary="Reorder all blocks on a project",
    description=(
        "Reorder every content block on a project page by supplying the complete "
        "ordered array of block UUIDs. The server assigns position 0, 1, 2 … in "
        "the order they appear in `block_ids`. The array **must** contain every "
        "block UUID for this project — subsets are rejected with 400."
    ),
)
def reorder_blocks(
    project_id: uuid.UUID,
    body: ReorderBlocksRequest,
    current_admin: Users = Depends(get_current_admin),
    use_case: ReorderBlocks = Depends(get_reorder_blocks),
) -> ReorderBlocksResponse:
    cmd = ReorderBlocksCommand(
        project_id=project_id,
        requester_id=current_admin.id,
        block_ids=list(body.block_ids),
    )

    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc
    except BlockReorderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc

    return ReorderBlocksResponse(success=True, block_count=result.block_count)


@router.delete(
    "/{project_id}/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a block",
    description=(
        "Permanently remove a content block from a project. "
        "Remaining blocks keep their positions — call the reorder endpoint afterwards "
        "to normalize if needed. A project with zero blocks is valid."
    ),
)
def delete_block(
    project_id: uuid.UUID,
    block_id: uuid.UUID,
    current_admin: Users = Depends(get_current_admin),
    use_case: DeleteBlock = Depends(get_delete_block),
) -> None:
    try:
        use_case.execute(project_id, block_id, current_admin.id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "BLOCK_NOT_FOUND", "message": "Block not found on this project"},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc


@router.put(
    "/{project_id}/blocks/{block_id}",
    status_code=status.HTTP_200_OK,
    response_model=BlockResponse,
    summary="Update a block",
    description=(
        "Update an existing block's `config` and/or `position`. Both fields are "
        "optional — send only what changed. `block_type` is immutable and is "
        "silently ignored if present. The incoming `config` is shallow-merged "
        "onto the stored config (so a partial update never wipes untouched "
        "keys) and re-validated against the block's type before saving; an "
        "empty `config` `{}` is a valid no-op. A block on a different project "
        "is reported as `404 BLOCK_NOT_FOUND` (its existence is never leaked)."
    ),
)
def update_block(
    project_id: uuid.UUID,
    block_id: uuid.UUID,
    body: UpdateBlockRequest,
    current_admin: Users = Depends(get_current_admin),
    use_case: UpdateBlock = Depends(get_update_block),
) -> BlockResponse:
    cmd = UpdateBlockCommand(
        project_id=project_id,
        block_id=block_id,
        requester_id=current_admin.id,
        position=body.position,
        config=body.config,
    )

    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "BLOCK_NOT_FOUND", "message": str(exc)},
        ) from exc
    except CodeTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "CODE_TOO_LONG", "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    return BlockResponse(
        id=result.id,
        project_id=result.project_id,
        block_type=result.block_type,
        position=result.position,
        config=result.config,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


# IMPORTANT: this route MUST be registered before /{project_id}.
# FastAPI matches routes in declaration order; registering /slug-check after
# /{project_id} causes FastAPI to parse "slug-check" as a UUID and return 422.
@router.get(
    "/slug-check",
    status_code=status.HTTP_200_OK,
    response_model=SlugCheckResponse,
    summary="Check slug availability",
    description=(
        "Checks whether a given slug is available before the user saves the project. "
        "The slug is normalized (lowercase, spaces→hyphens, special chars stripped) before "
        "the DB check; the normalized form is returned in the response. "
        "Pass `exclude_id` when editing an existing project so its own current slug is "
        "not reported as taken. Reserved slugs (`admin`, `api`, `auth`, `health`, `login`, "
        "`logout`, `me`, `settings`) are never available regardless of DB state."
    ),
)
def check_slug_availability(
    slug: str | None = None,
    exclude_id: str | None = None,
    _: Users = Depends(get_current_admin),
    use_case: CheckSlugAvailability = Depends(get_check_slug_availability),
) -> SlugCheckResponse:
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MISSING_PARAM", "message": "slug query parameter is required"},
        )

    parsed_exclude_id: uuid.UUID | None = None
    if exclude_id:
        try:
            parsed_exclude_id = uuid.UUID(exclude_id)
        except ValueError:
            parsed_exclude_id = None

    cmd = CheckSlugCommand(slug=slug, exclude_id=parsed_exclude_id)

    try:
        result = use_case.execute(cmd)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_SLUG", "message": str(exc)},
        ) from exc

    return SlugCheckResponse(
        slug=result.slug,
        available=result.available,
        suggested=result.suggested,
    )


@router.get(
    "/{project_id}",
    status_code=status.HTTP_200_OK,
    response_model=GetProjectResponse,
    summary="Load an existing project",
    description=(
        "Load a project by ID for the admin edit page (`/admin/projects/{id}/edit`). "
        "Returns the project with its content blocks ordered by `position`. "
        "Responds `404 PROJECT_NOT_FOUND` when the ID is unknown, "
        "`403 FORBIDDEN` when the project belongs to another author, "
        "and `422 VALIDATION_ERROR` when the ID is not a valid UUID."
    ),
)
def get_project(
    project_id: uuid.UUID,
    current_admin: Users = Depends(get_current_admin),
    use_case: GetProject = Depends(get_get_project),
) -> GetProjectResponse:
    try:
        result = use_case.execute(project_id, current_admin.id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": str(exc)},
        ) from exc

    return GetProjectResponse(
        id=result.id,
        title=result.title,
        slug=result.slug,
        excerpt=result.excerpt,
        thumbnail_url=result.thumbnail_url,
        tech_stack=result.tech_stack,
        template_id=result.template_id,
        github_url=result.github_url,
        demo_url=result.demo_url,
        status=result.status,
        visibility=result.visibility,
        is_featured=result.is_featured,
        views=result.views,
        seo=SeoResponse(
            meta_title=result.seo.get("meta_title"),
            meta_description=result.seo.get("meta_description"),
            og_image_url=result.seo.get("og_image_url"),
            canonical_url=result.seo.get("canonical_url"),
        ),
        blocks=[
            BlockResponse(
                id=b.id,
                project_id=b.project_id,
                block_type=b.block_type,
                position=b.position,
                config=b.config,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in result.blocks
        ],
        author_id=result.author_id,
        published_at=result.published_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )

"""Admin project endpoints — create draft project (presentation layer).

Thin controller: parse the request, call the use case, translate domain errors
to HTTP, serialize the result. No business logic here.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_create_project, get_delete_project, get_get_project, get_update_project
from app.api.v1.schemas.project import (
    BlockResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    GetProjectResponse,
    SeoResponse,
    UpdateProjectRequest,
    UpdateProjectResponse,
)
from app.application.dtos.project import CreateProjectCommand, SeoInput, UpdateProjectCommand
from app.application.use_cases.projects.create_project import CreateProject
from app.application.use_cases.projects.delete_project import DeleteProject
from app.application.use_cases.projects.get_project import GetProject
from app.application.use_cases.projects.update_project import UpdateProject
from app.domain.exceptions import NotFoundError, PermissionError, SlugTakenError, ValidationError
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


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
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

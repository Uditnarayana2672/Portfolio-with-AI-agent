"""Admin project endpoints — create draft project (presentation layer).

Thin controller: parse the request, call the use case, translate domain errors
to HTTP, serialize the result. No business logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_create_project
from app.api.v1.schemas.project import (
    CreateProjectRequest,
    CreateProjectResponse,
    SeoResponse,
)
from app.application.dtos.project import CreateProjectCommand, SeoInput
from app.application.use_cases.projects.create_project import CreateProject
from app.domain.exceptions import ValidationError
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

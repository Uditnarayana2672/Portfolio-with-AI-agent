"""Public (unauthenticated) project endpoints — presentation layer.

These power the public-facing project detail page. No auth: only *published*,
publicly-visible projects are ever returned. Drafts, archived, or members-only
projects respond 404 so their existence is never leaked.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.providers import (
    get_get_public_project,
    get_react_to_project,
)
from app.api.v1.schemas.project import (
    BlockResponse,
    PublicProjectNeighborResponse,
    PublicProjectResponse,
    ReactToProjectRequest,
    ReactToProjectResponse,
    SeoResponse,
)
from app.application.dtos.project import ReactToProjectCommand
from app.application.use_cases.projects.get_public_project import GetPublicProject
from app.application.use_cases.projects.react_to_project import ReactToProject
from app.domain.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/projects", tags=["Public Projects"])


def _neighbor(n) -> PublicProjectNeighborResponse | None:
    if n is None:
        return None
    return PublicProjectNeighborResponse(
        title=n.title,
        slug=n.slug,
        excerpt=n.excerpt,
        thumbnail_url=n.thumbnail_url,
    )


@router.get(
    "/{slug}",
    status_code=status.HTTP_200_OK,
    response_model=PublicProjectResponse,
    summary="Get a published project by slug (public)",
    description=(
        "Public, unauthenticated read of a published project and its content "
        "blocks for the project detail page. Increments the view counter. "
        "Only `published` projects with `public`/`unlisted` visibility are "
        "returned; anything else responds 404."
    ),
)
def get_public_project(
    slug: str,
    use_case: GetPublicProject = Depends(get_get_public_project),
) -> PublicProjectResponse:
    try:
        result = use_case.execute(slug)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc

    return PublicProjectResponse(
        id=result.id,
        title=result.title,
        slug=result.slug,
        excerpt=result.excerpt,
        thumbnail_url=result.thumbnail_url,
        tech_stack=result.tech_stack,
        template_id=result.template_id,
        github_url=result.github_url,
        demo_url=result.demo_url,
        views=result.views,
        seo=SeoResponse(
            meta_title=result.seo.get("meta_title"),
            meta_description=result.seo.get("meta_description"),
            og_image_url=result.seo.get("og_image_url"),
            canonical_url=result.seo.get("canonical_url"),
        ),
        meta=result.meta,
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
        reactions=result.reactions,
        prev_project=_neighbor(result.prev_project),
        next_project=_neighbor(result.next_project),
        published_at=result.published_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post(
    "/{slug}/reactions",
    status_code=status.HTTP_200_OK,
    response_model=ReactToProjectResponse,
    summary="React to a published project (public)",
    description=(
        "Record an anonymous reaction (like / love / fire / clap / mind_blown) "
        "on a published project and return the updated per-type counts."
    ),
)
def react_to_project(
    slug: str,
    body: ReactToProjectRequest,
    use_case: ReactToProject = Depends(get_react_to_project),
) -> ReactToProjectResponse:
    cmd = ReactToProjectCommand(
        slug=slug,
        reaction_type=body.reaction_type,
        session_id=body.session_id,
    )
    try:
        result = use_case.execute(cmd)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    return ReactToProjectResponse(slug=result.slug, reactions=result.reactions)

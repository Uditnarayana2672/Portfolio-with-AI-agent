"""GetProject use case (application layer).

Loads a project with its blocks for the admin edit page.
"""
from __future__ import annotations

import uuid

from app.application.dtos.project import BlockResult, GetProjectResult
from app.domain.exceptions import NotFoundError, PermissionError
from app.domain.repositories.project_repository import ProjectRepository


class GetProject:
    def __init__(self, *, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, project_id: uuid.UUID, requester_id: uuid.UUID) -> GetProjectResult:
        pair = self._repo.get_with_blocks(project_id)
        if pair is None:
            raise NotFoundError(f"Project {project_id} not found.")

        project, blocks = pair

        if project.author_id != requester_id:
            raise PermissionError("You do not have access to this project.")

        return GetProjectResult(
            id=project.id,
            title=project.title,
            slug=project.slug,
            excerpt=project.excerpt,
            thumbnail_url=project.thumbnail_url,
            tech_stack=project.tech_stack,
            template_id=project.template_id,
            github_url=project.github_url,
            demo_url=project.demo_url,
            status=project.status,
            visibility=project.visibility,
            is_featured=project.is_featured,
            views=project.views,
            seo=project.seo,
            blocks=[
                BlockResult(
                    id=b.id,
                    project_id=b.project_id,
                    block_type=b.block_type,
                    position=b.position,
                    config=b.config,
                    created_at=b.created_at,
                    updated_at=b.updated_at,
                )
                for b in blocks
            ],
            author_id=project.author_id,
            published_at=project.published_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

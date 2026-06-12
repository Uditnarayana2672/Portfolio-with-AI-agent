"""DeleteBlock use case (application layer).

Verifies the project belongs to the requester and the block exists on it,
then permanently removes the block.
No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

import uuid

from app.domain.exceptions import NotFoundError, PermissionError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.block_repository import BlockRepository
from app.domain.repositories.project_repository import ProjectRepository


class DeleteBlock:
    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        block_repo: BlockRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._project_repo = project_repo
        self._block_repo = block_repo
        self._activity = activity

    def execute(
        self,
        project_id: uuid.UUID,
        block_id: uuid.UUID,
        requester_id: uuid.UUID,
    ) -> None:
        pair = self._project_repo.get_with_blocks(project_id)
        if pair is None:
            raise NotFoundError(f"Block {block_id} not found on project {project_id}.")
        project, _ = pair

        if project.author_id != requester_id:
            raise PermissionError("You do not have access to this project.")

        block = self._block_repo.get_for_project(block_id, project_id)
        if block is None:
            raise NotFoundError(f"Block {block_id} not found on project {project_id}.")

        self._block_repo.delete(block_id)

        self._activity.record(
            action_type="project_updated",
            description=f"Block '{block.block_type}' deleted from project '{project.title}'.",
            entity_type="project",
            entity_id=project_id,
            entity_title=project.title,
            performed_by=requester_id,
        )

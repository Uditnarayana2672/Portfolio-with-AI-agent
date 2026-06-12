"""DeleteProject use case (application layer).

Verifies the project exists and belongs to the requester, then permanently
deletes it. The DB cascade removes child blocks automatically.
No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

import uuid

from app.domain.exceptions import NotFoundError, PermissionError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.project_repository import ProjectRepository


class DeleteProject:
    def __init__(
        self,
        *,
        repo: ProjectRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._repo = repo
        self._activity = activity

    def execute(self, project_id: uuid.UUID, requester_id: uuid.UUID) -> None:
        pair = self._repo.get_with_blocks(project_id)
        if pair is None:
            raise NotFoundError(f"Project {project_id} not found.")

        project, _ = pair

        if project.author_id != requester_id:
            raise PermissionError("You do not have access to this project.")

        title = project.title
        self._repo.delete(project_id)

        self._activity.record(
            action_type="project_deleted",
            description=f"Project '{title}' permanently deleted.",
            entity_type="project",
            entity_id=project_id,
            entity_title=title,
            performed_by=requester_id,
        )

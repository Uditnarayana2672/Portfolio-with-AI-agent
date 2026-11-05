"""PublishProject use case (application layer).

Validates publishability, transitions the project to 'published', and records
the activity. No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

from app.application.dtos.project import PublishProjectCommand, PublishProjectResult
from app.domain.exceptions import NotFoundError, PermissionError, PublishBlockedError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.project_repository import ProjectRepository


class PublishProject:
    def __init__(
        self,
        *,
        repo: ProjectRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._repo = repo
        self._activity = activity

    def execute(self, cmd: PublishProjectCommand) -> PublishProjectResult:
        pair = self._repo.get_with_blocks(cmd.project_id)
        if pair is None:
            raise NotFoundError(f"Project {cmd.project_id} not found.")
        project, blocks = pair

        if project.author_id != cmd.author_id:
            raise PermissionError("You do not have access to this project.")

        # Idempotent: already published → return current state without any mutation.
        if project.status == "published":
            return PublishProjectResult(
                id=project.id,
                slug=project.slug,
                status=project.status,
                published_at=project.published_at,
            )

        issues: list[str] = []
        if not project.title or not project.title.strip():
            issues.append("Title is required")
        if len(blocks) == 0:
            issues.append("At least 1 content block is required")
        meta_title = project.seo.get("meta_title")
        if not meta_title or not str(meta_title).strip():
            issues.append("Meta title is required for SEO")

        if issues:
            raise PublishBlockedError(issues)

        updated = self._repo.publish(cmd.project_id)

        self._activity.record(
            action_type="project_published",
            description=f"Project '{updated.title}' published.",
            entity_type="project",
            entity_id=updated.id,
            entity_title=updated.title,
            performed_by=cmd.author_id,
        )

        return PublishProjectResult(
            id=updated.id,
            slug=updated.slug,
            status=updated.status,
            published_at=updated.published_at,
        )

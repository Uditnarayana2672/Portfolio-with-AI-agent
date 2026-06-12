"""ToggleFeature use case (application layer).

Flips a project's ``is_featured`` flag from a lightweight, dedicated endpoint
(no full project payload required). Verifies the project exists and belongs to
the requester, short-circuits no-op toggles, and enforces the homepage featured
cap when turning the flag on.
No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

from app.application.dtos.project import (
    MAX_FEATURED_PROJECTS,
    ToggleFeatureCommand,
    ToggleFeatureResult,
)
from app.domain.exceptions import (
    FeaturedLimitError,
    NotFoundError,
    PermissionError,
)
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.project_repository import ProjectRepository


class ToggleFeature:
    def __init__(
        self,
        *,
        repo: ProjectRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._repo = repo
        self._activity = activity

    def execute(self, cmd: ToggleFeatureCommand) -> ToggleFeatureResult:
        pair = self._repo.get_with_blocks(cmd.project_id)
        if pair is None:
            raise NotFoundError(f"Project {cmd.project_id} not found.")
        project, _ = pair

        if project.author_id != cmd.requester_id:
            raise PermissionError("You do not have access to this project.")

        # No-op: already in the requested state. Skip the write, the limit check,
        # and the activity log entirely (so re-asserting an already-featured
        # project never trips the cap).
        if project.is_featured == cmd.is_featured:
            return ToggleFeatureResult(id=project.id, is_featured=project.is_featured)

        # Enforce the homepage cap only when turning the flag ON.
        if cmd.is_featured:
            others_featured = self._repo.count_featured_excluding(project.id)
            if others_featured >= MAX_FEATURED_PROJECTS:
                raise FeaturedLimitError(MAX_FEATURED_PROJECTS)

        updated, _ = self._repo.update(cmd.project_id, {"is_featured": cmd.is_featured})

        verb = "featured" if cmd.is_featured else "unfeatured"
        self._activity.record(
            action_type="project_updated",
            description=f"Project '{updated.title}' {verb}.",
            entity_type="project",
            entity_id=updated.id,
            entity_title=updated.title,
            performed_by=cmd.requester_id,
        )

        return ToggleFeatureResult(id=updated.id, is_featured=updated.is_featured)

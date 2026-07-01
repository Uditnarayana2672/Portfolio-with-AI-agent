"""ReactToProject use case (application layer).

Records an anonymous public reaction (like / love / fire / clap / mind_blown)
on a published project and returns the updated per-type counts.
"""
from __future__ import annotations

from app.application.dtos.project import (
    ALLOWED_REACTION_TYPES,
    ReactToProjectCommand,
    ReactToProjectResult,
)
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.repositories.project_repository import ProjectRepository


class ReactToProject:
    def __init__(self, *, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, cmd: ReactToProjectCommand) -> ReactToProjectResult:
        if cmd.reaction_type not in ALLOWED_REACTION_TYPES:
            raise ValidationError(
                f"reaction_type must be one of: {sorted(ALLOWED_REACTION_TYPES)}"
            )

        pair = self._repo.get_published_by_slug(cmd.slug)
        if pair is None:
            raise NotFoundError(f"Project '{cmd.slug}' not found.")
        project, _ = pair

        counts = self._repo.add_reaction(
            project.id, cmd.reaction_type, cmd.session_id
        )
        return ReactToProjectResult(slug=cmd.slug, reactions=counts)

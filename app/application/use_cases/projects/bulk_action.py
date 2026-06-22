"""BulkAction use case (application layer).

Executes one operation across multiple projects atomically.
All project IDs must belong to the authenticated admin; any foreign ID returns
403 and aborts the entire operation.
"""
from __future__ import annotations

import uuid

from app.application.dtos.project import (
    ALLOWED_BULK_ACTIONS,
    MAX_FEATURED_PROJECTS,
    BulkActionCommand,
    BulkActionResult,
)
from app.domain.exceptions import BulkPermissionError, ConflictError, ValidationError
from app.domain.repositories.project_repository import ProjectRepository


class BulkAction:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, cmd: BulkActionCommand) -> BulkActionResult:
        if cmd.action not in ALLOWED_BULK_ACTIONS:
            raise ValidationError(
                f"action {cmd.action!r} is not valid. "
                f"Allowed: {sorted(ALLOWED_BULK_ACTIONS)}"
            )
        if not cmd.project_ids:
            raise ValidationError("project_ids must not be empty.")

        # Verify all IDs belong to the requesting admin.
        owned_ids = set(self._repo.get_owned_ids(cmd.project_ids, cmd.author_id))
        foreign_ids = [pid for pid in cmd.project_ids if pid not in owned_ids]
        if foreign_ids:
            raise BulkPermissionError(foreign_ids=foreign_ids)

        project_ids = list(owned_ids)
        requested = len(project_ids)

        if cmd.action == "publish":
            mutated = self._repo.bulk_update_status(project_ids, "published", cmd.author_id)
            return BulkActionResult(
                action=cmd.action,
                requested=requested,
                succeeded=len(mutated),
                failed=0,
                skipped=requested - len(mutated),
                project_ids=mutated,
            )

        if cmd.action == "archive":
            mutated = self._repo.bulk_update_status(project_ids, "archived", cmd.author_id)
            return BulkActionResult(
                action=cmd.action,
                requested=requested,
                succeeded=len(mutated),
                failed=0,
                skipped=requested - len(mutated),
                project_ids=mutated,
            )

        if cmd.action == "delete":
            mutated = self._repo.bulk_delete(project_ids, cmd.author_id)
            return BulkActionResult(
                action=cmd.action,
                requested=requested,
                succeeded=len(mutated),
                failed=0,
                skipped=requested - len(mutated),
                project_ids=mutated,
            )

        if cmd.action in ("feature", "unfeature"):
            is_featured = cmd.action == "feature"
            if is_featured:
                # Count currently featured projects (pass a UUID that matches nothing
                # to get the true total — we want all featured, not excluding anything).
                current_featured = self._repo.count_featured_excluding(uuid.UUID(int=0))
                if current_featured + len(project_ids) > MAX_FEATURED_PROJECTS:
                    raise ConflictError(
                        f"Featuring these projects would exceed the maximum of "
                        f"{MAX_FEATURED_PROJECTS} featured projects."
                    )
            mutated = self._repo.bulk_set_featured(project_ids, is_featured, cmd.author_id)
            return BulkActionResult(
                action=cmd.action,
                requested=requested,
                succeeded=len(mutated),
                failed=0,
                skipped=requested - len(mutated),
                project_ids=mutated,
            )

        raise ValidationError(f"Unhandled action: {cmd.action!r}")

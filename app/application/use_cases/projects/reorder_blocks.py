"""ReorderBlocks use case (application layer).

Validates that the supplied block_ids array is the complete, duplicate-free
set of IDs belonging to this project, then atomically assigns positions
0, 1, 2 … in the given order. No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

from app.application.dtos.project import ReorderBlocksCommand, ReorderBlocksResult
from app.domain.exceptions import BlockReorderError, NotFoundError, PermissionError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.block_repository import BlockRepository
from app.domain.repositories.project_repository import ProjectRepository


class ReorderBlocks:
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

    def execute(self, cmd: ReorderBlocksCommand) -> ReorderBlocksResult:
        pair = self._project_repo.get_with_blocks(cmd.project_id)
        if pair is None:
            raise NotFoundError(f"Project {cmd.project_id} not found.")
        project, existing_blocks = pair

        if project.author_id != cmd.requester_id:
            raise PermissionError("You do not have access to this project.")

        if not cmd.block_ids:
            raise BlockReorderError(
                "EMPTY_BLOCK_IDS",
                "block_ids array cannot be empty",
            )

        if len(cmd.block_ids) != len(set(cmd.block_ids)):
            raise BlockReorderError(
                "DUPLICATE_BLOCK_IDS",
                "block_ids array contains duplicate values",
            )

        if len(cmd.block_ids) != len(existing_blocks):
            raise BlockReorderError(
                "BLOCK_IDS_MISMATCH",
                f"block_ids count ({len(cmd.block_ids)}) does not match "
                f"project block count ({len(existing_blocks)})",
            )

        existing_ids = {b.id for b in existing_blocks}
        for block_id in cmd.block_ids:
            if block_id not in existing_ids:
                raise BlockReorderError(
                    "INVALID_BLOCK_ID",
                    f"Block {block_id} does not belong to this project",
                )

        self._block_repo.reorder(cmd.project_id, cmd.block_ids)

        self._activity.record(
            action_type="project_updated",
            description=f"Blocks reordered on project '{project.title}'.",
            entity_type="project",
            entity_id=project.id,
            entity_title=project.title,
            performed_by=cmd.requester_id,
        )

        return ReorderBlocksResult(block_count=len(cmd.block_ids))

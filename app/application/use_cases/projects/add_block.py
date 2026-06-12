"""AddBlock use case (application layer).

Verifies the project exists and belongs to the requester, enforces per-type
business rules (poll option count, code length), clamps the position to the
current block count, shifts colliding blocks down, and persists the new block.
No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

from app.application.dtos.project import (
    MAX_CODE_LENGTH,
    MAX_POLL_OPTIONS,
    MIN_POLL_OPTIONS,
    SUPPORTED_BLOCK_TYPES,
    AddBlockCommand,
    BlockResult,
)
from app.domain.exceptions import (
    CodeTooLongError,
    NotFoundError,
    PermissionError,
    ValidationError,
)
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.block_repository import BlockRepository, NewBlock
from app.domain.repositories.project_repository import ProjectRepository


class AddBlock:
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

    def execute(self, cmd: AddBlockCommand) -> BlockResult:
        pair = self._project_repo.get_with_blocks(cmd.project_id)
        if pair is None:
            raise NotFoundError(f"Project {cmd.project_id} not found.")
        project, existing_blocks = pair

        if project.author_id != cmd.requester_id:
            raise PermissionError("You do not have access to this project.")

        if cmd.block_type not in SUPPORTED_BLOCK_TYPES:
            raise ValidationError(f"block_type '{cmd.block_type}' is not supported")

        self._validate_business_rules(cmd.block_type, cmd.config)

        # Clamp out-of-range positions to "append at end" rather than erroring;
        # negative positions become 0 (first).
        position = max(0, min(cmd.position, len(existing_blocks)))

        # Make room: blocks at the requested position or later move down by one.
        # Shift + insert flush on the same session, so they commit atomically.
        self._block_repo.shift_positions_from(cmd.project_id, position)

        block = self._block_repo.add(
            NewBlock(
                project_id=cmd.project_id,
                block_type=cmd.block_type,
                position=position,
                config=cmd.config,
            )
        )

        self._activity.record(
            action_type="project_updated",
            description=f"Block '{block.block_type}' added to project '{project.title}'.",
            entity_type="project",
            entity_id=project.id,
            entity_title=project.title,
            performed_by=cmd.requester_id,
        )

        return BlockResult(
            id=block.id,
            project_id=block.project_id,
            block_type=block.block_type,
            position=block.position,
            config=block.config,
            created_at=block.created_at,
            updated_at=block.updated_at,
        )

    @staticmethod
    def _validate_business_rules(block_type: str, config: dict) -> None:
        if block_type == "poll":
            options = config.get("options") or []
            if len(options) < MIN_POLL_OPTIONS:
                raise ValidationError(
                    f"poll.options must have at least {MIN_POLL_OPTIONS} items"
                )
            if len(options) > MAX_POLL_OPTIONS:
                raise ValidationError(
                    f"poll.options cannot have more than {MAX_POLL_OPTIONS} items"
                )
        elif block_type == "code":
            if len(config.get("code") or "") > MAX_CODE_LENGTH:
                raise CodeTooLongError(
                    "code content cannot exceed 50,000 characters"
                )

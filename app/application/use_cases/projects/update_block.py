"""UpdateBlock use case (application layer).

Updates the ``config`` and/or ``position`` of an existing block. ``block_type``
is immutable. Incoming config is shallow-merged into the stored config and the
result is re-validated against the schema for the block's type before saving.
No SQL, no HTTP, no framework imports.

Scoping note: the block is looked up by (block_id, project_id) together, so a
block on a different project is indistinguishable from a missing one — both
yield 404, never leaking that the block exists elsewhere (no 403 here, by
contract).
"""
from __future__ import annotations

from app.application.dtos.project import (
    BlockResult,
    UpdateBlockCommand,
)
from app.application.interfaces.block_config_validator import BlockConfigValidator
from app.application.use_cases.projects.block_rules import validate_block_business_rules
from app.domain.exceptions import NotFoundError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.block_repository import BlockRepository


class UpdateBlock:
    def __init__(
        self,
        *,
        block_repo: BlockRepository,
        config_validator: BlockConfigValidator,
        activity: ActivityLogRepository,
    ) -> None:
        self._block_repo = block_repo
        self._validator = config_validator
        self._activity = activity

    def execute(self, cmd: UpdateBlockCommand) -> BlockResult:
        existing = self._block_repo.get_for_project(cmd.block_id, cmd.project_id)
        if existing is None:
            raise NotFoundError("Block not found on this project")

        # ── config: shallow-merge the incoming partial onto the stored config,
        #    then re-validate the merged result against the type's schema. ──────
        new_config: dict | None = None
        if cmd.config is not None:
            merged = {**existing.config, **cmd.config}
            validated = self._validator.validate(existing.block_type, merged)
            validate_block_business_rules(existing.block_type, validated)
            if validated != existing.config:
                new_config = validated

        # ── position: set directly (a separate reorder endpoint normalizes). ──
        new_position: int | None = None
        if cmd.position is not None and cmd.position != existing.position:
            new_position = cmd.position

        # Nothing actually changed → no write, no updated_at bump, no audit noise.
        if new_config is None and new_position is None:
            return self._to_result(existing)

        updated = self._block_repo.update_block(
            cmd.block_id, config=new_config, position=new_position
        )

        self._activity.record(
            action_type="project_updated",
            description=f"Block '{updated.block_type}' updated.",
            entity_type="project",
            entity_id=updated.project_id,
            performed_by=cmd.requester_id,
        )

        return self._to_result(updated)

    @staticmethod
    def _to_result(block) -> BlockResult:
        return BlockResult(
            id=block.id,
            project_id=block.project_id,
            block_type=block.block_type,
            position=block.position,
            config=block.config,
            created_at=block.created_at,
            updated_at=block.updated_at,
        )

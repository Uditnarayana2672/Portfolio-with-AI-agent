"""Shared per-type business rules for block config (application layer).

Pydantic enforces config *shape* (required fields, types). These rules cover
the business *caps* that intentionally live with the application logic so they
raise domain errors with the exact documented messages — shared by both the
AddBlock and UpdateBlock use cases.
"""
from __future__ import annotations

from app.application.dtos.project import (
    MAX_CODE_LENGTH,
    MAX_POLL_OPTIONS,
    MIN_POLL_OPTIONS,
)
from app.domain.exceptions import CodeTooLongError, ValidationError


def validate_block_business_rules(block_type: str, config: dict) -> None:
    """Enforce poll option count (2–6) and code length (≤ 50 000) caps.

    Raises ``ValidationError`` / ``CodeTooLongError`` with the documented
    messages. A no-op for every other block type.
    """
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
            raise CodeTooLongError("code content cannot exceed 50,000 characters")

"""Block domain entity (core layer).

Framework-free representation of a project content block.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    id: uuid.UUID
    project_id: uuid.UUID
    block_type: str
    position: int
    config: dict
    created_at: datetime.datetime
    updated_at: datetime.datetime

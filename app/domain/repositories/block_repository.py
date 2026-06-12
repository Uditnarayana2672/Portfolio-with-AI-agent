"""BlockRepository port (domain layer).

Abstract contract for persisting/querying project content blocks.
The application layer depends on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities.block import Block


@dataclass(frozen=True)
class NewBlock:
    """The fields needed to persist a freshly created content block. Distinct
    from the ``Block`` entity, which also carries server-assigned id/timestamps."""

    project_id: uuid.UUID
    block_type: str
    position: int
    config: dict


class BlockRepository(ABC):
    @abstractmethod
    def get_for_project(self, block_id: uuid.UUID, project_id: uuid.UUID) -> Block | None:
        """Return the block only if it belongs to the given project, otherwise None.
        Queries by both IDs so a block on a different project is indistinguishable
        from a missing block — callers never need to cross-check ownership."""

    @abstractmethod
    def shift_positions_from(self, project_id: uuid.UUID, position: int) -> None:
        """Shift every block of the project at ``position`` or later down by one
        (position + 1), making room for an insert. Runs in the request's open
        transaction so shift + insert commit (or roll back) together. Flushes."""

    @abstractmethod
    def add(self, new: NewBlock) -> Block:
        """Persist a new block and return it with server-assigned id/timestamps.
        Flushes so the id is available; the request's session owns the commit."""

    @abstractmethod
    def update_block(
        self,
        block_id: uuid.UUID,
        *,
        config: dict | None = None,
        position: int | None = None,
    ) -> Block:
        """Update a block's ``config`` and/or ``position`` and bump ``updated_at``.

        Only non-None arguments are applied (``block_type`` is immutable and
        never updatable here). The caller must have verified the block exists
        and belongs to the project. Flushes and returns the refreshed block;
        the request's session owns the commit."""

    @abstractmethod
    def delete(self, block_id: uuid.UUID) -> None:
        """Permanently delete a block by id. Caller must verify existence first.
        Flushes; the request's session owns the commit."""

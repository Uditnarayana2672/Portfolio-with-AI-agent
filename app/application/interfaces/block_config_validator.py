"""Port: per-type block config validator (application layer).

The UpdateBlock use case must re-validate a *merged* config (existing + the
incoming partial) against the schema for the block's type. The merge depends on
stored state, so validation happens inside the use case rather than at the HTTP
edge. The use case depends on THIS abstraction; the concrete implementation
(built on the presentation-layer Pydantic models) is wired in the composition
root, keeping the application layer free of any framework/schema imports.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BlockConfigValidator(ABC):
    @abstractmethod
    def validate(self, block_type: str, config: dict) -> dict:
        """Validate ``config`` against the schema for ``block_type`` and return
        the normalized config (defaults applied).

        Raises ``app.domain.exceptions.ValidationError`` when the config does
        not match the schema for the type.
        """

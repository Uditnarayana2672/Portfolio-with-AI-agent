"""Every block type the backend accepts must have a public renderer.

Stops a new block type silently disappearing from project pages. Skipped when
the UI repo isn't checked out next to this one.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.v1.schemas.block_config import BLOCK_CONFIG_MODELS

RENDERER = Path(__file__).resolve().parents[2] / "Portfolio_UI/packages/shared/src/blocks/Blocks.tsx"


def test_backend_block_types_all_have_a_public_renderer():
    if not RENDERER.exists():
        pytest.skip("UI repo not checked out")
    source = RENDERER.read_text()
    listed = set(re.findall(r"'([a-z]+)'", source[source.index("BLOCK_TYPES = ["): source.index("] as const")]))
    handled = set(re.findall(r"case '([a-z]+)':", source))
    assert set(BLOCK_CONFIG_MODELS) == listed
    assert set(BLOCK_CONFIG_MODELS) == handled

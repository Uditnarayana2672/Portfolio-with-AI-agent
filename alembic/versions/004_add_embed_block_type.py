"""Allow the `embed` block type on project_blocks.

Adds `embed` to the project_blocks.block_type CHECK constraint so generic
third-party embeds (CodeSandbox, Figma, live demos, …) can be persisted.

Revision ID: 004
Revises: 003
Create Date: 2026-06-25 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None

_TYPES = (
    "'hero','text','image','code','video','comparison','poll','stats',"
    "'quote','gallery','timeline','cta','form'"
)


def upgrade() -> None:
    op.execute(text("ALTER TABLE project_blocks DROP CONSTRAINT IF EXISTS project_blocks_block_type_check"))
    op.execute(text(
        "ALTER TABLE project_blocks ADD CONSTRAINT project_blocks_block_type_check "
        f"CHECK (block_type = ANY (ARRAY[{_TYPES},'embed']::text[]))"
    ))


def downgrade() -> None:
    op.execute(text("ALTER TABLE project_blocks DROP CONSTRAINT IF EXISTS project_blocks_block_type_check"))
    op.execute(text(
        "ALTER TABLE project_blocks ADD CONSTRAINT project_blocks_block_type_check "
        f"CHECK (block_type = ANY (ARRAY[{_TYPES}]::text[]))"
    ))

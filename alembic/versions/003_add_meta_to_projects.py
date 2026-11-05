"""Add editorial `meta` JSONB column to projects.

Holds the public project-detail page-header metadata (role, timeline_label,
status_label, recognition, category/kicker, hero_caption, …) authored by the
admin. Free-form JSON so new header fields never need another migration.

Revision ID: 003
Revises: 002
Create Date: 2026-06-25 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "ALTER TABLE projects "
        "ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb"
    ))


def downgrade() -> None:
    op.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS meta"))

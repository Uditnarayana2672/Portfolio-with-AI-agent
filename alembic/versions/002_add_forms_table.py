"""Add forms table.

Revision ID: 002
Revises: 001
Create Date: 2026-06-14 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS forms (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            author_id   UUID        NOT NULL REFERENCES users(id),
            name        TEXT        NOT NULL,
            form_type   TEXT        NOT NULL DEFAULT 'custom'
                            CHECK (form_type IN ('contact', 'discovery', 'feedback', 'waitlist', 'custom')),
            config      JSONB       NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT forms_pkey PRIMARY KEY (id)
        )
    """))
    op.execute(text("CREATE INDEX IF NOT EXISTS idx_forms_author ON forms (author_id)"))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS forms"))

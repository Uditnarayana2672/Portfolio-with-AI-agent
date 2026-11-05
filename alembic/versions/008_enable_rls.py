"""Enable Row Level Security on the public tables that had it off.

Mirror of supabase/migrations/008_enable_rls.sql (the source applied in Supabase).

Revision ID: 008
Revises: 007
Create Date: 2026-11-05 00:00:00.000000
"""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "008_enable_rls.sql"


def upgrade() -> None:
    op.execute(text(_SQL.read_text()))


def downgrade() -> None:
    op.execute(text(_SQL.read_text().replace("enable row level security", "disable row level security")))

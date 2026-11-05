"""Portfolio content document: single-row table and activity type.

Mirror of supabase/migrations/007_portfolio_content.sql (the source applied in
Supabase).

Revision ID: 007
Revises: 006
Create Date: 2026-11-05 00:00:00.000000
"""
from __future__ import annotations

from pathlib import Path

from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "007_portfolio_content.sql"


def upgrade() -> None:
    # exec_driver_sql: the seed JSON must not be parsed for :bind parameters.
    op.get_bind().exec_driver_sql(_SQL.read_text().replace("%", "%%"))


def downgrade() -> None:
    # Postgres cannot drop an enum value; 'portfolio_updated' stays, unused.
    op.execute("drop table if exists public.portfolio_content")

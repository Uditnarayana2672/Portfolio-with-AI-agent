"""Public site support: poll/block link, newsletter opt-in, site rebuild tracking.

Mirror of supabase/migrations/009_public_site.sql (the source applied in Supabase).

Revision ID: 009
Revises: 008
Create Date: 2026-11-05 00:00:00.000000
"""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "009_public_site.sql"


def upgrade() -> None:
    op.execute(text(_SQL.read_text()))


def downgrade() -> None:
    # Postgres cannot drop an enum value; 'pending' stays, unused.
    op.execute(text("""
        drop table if exists public.site_builds;
        drop table if exists public.newsletter_sends;
        alter table public.newsletter_subscribers
          drop column if exists confirmed_at, drop column if exists confirm_expires_at,
          drop column if exists confirm_token;
        drop index if exists public.poll_votes_one_per_session;
        alter table public.polls drop column if exists block_id;
        alter table public.users alter column role set default 'admin';
    """))

"""Blog Manager schema: archive timestamp, weighted search vector, list index.

Adds blog_posts.archived_at (with a check tying it to status = 'archived'), a
generated weighted tsvector for ranked search, an index for the default list
order, and ON DELETE CASCADE on comments.blog_id so deleting a post with
comments doesn't fail.

Mirror of supabase/migrations/006_blog_manager.sql (the source applied in
Supabase).

Revision ID: 006
Revises: 005
Create Date: 2026-11-04 00:00:00.000000
"""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "006_blog_manager.sql"


def upgrade() -> None:
    op.execute(text(_SQL.read_text()))


def downgrade() -> None:
    op.execute(text("""
        alter table public.comments drop constraint if exists comments_blog_id_fkey,
          add constraint comments_blog_id_fkey
          foreign key (blog_id) references public.blog_posts(id);
        drop index if exists public.idx_blog_posts_status_updated;
        drop index if exists public.idx_blog_posts_search_vector;
        alter table public.blog_posts drop constraint if exists blog_posts_archived_has_time;
        alter table public.blog_posts drop column if exists search_vector, drop column if exists archived_at;
    """))

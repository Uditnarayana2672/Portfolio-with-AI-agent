"""Blog editor schema: working-copy columns, revisions, slug redirects.

Adds the columns the blog editor needs on blog_posts (subtitle, rendered
content, version lock, live revision pointer, schedule error…), the
blog_post_revisions and blog_slug_redirects tables, integrity checks, search
indexes, category sort order and the five seed categories.

Mirror of supabase/migrations/005_blog_editor_schema.sql (the source applied in
Supabase).

Revision ID: 005
Revises: 004
Create Date: 2026-11-03 00:00:00.000000
"""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "005_blog_editor_schema.sql"


def upgrade() -> None:
    op.execute(text(_SQL.read_text()))


def downgrade() -> None:
    op.execute(text("""
        drop index if exists public.uq_blog_categories_name_ci;
        alter table public.blog_categories drop column if exists sort_order;
        drop index if exists public.idx_blog_posts_due;
        drop index if exists public.idx_blog_posts_title_trgm;
        drop index if exists public.idx_blog_posts_search;
        create index idx_blog_posts_search on public.blog_posts using gin (
          to_tsvector('english', coalesce(title,'') || ' ' || coalesce(excerpt,'')));
        create index if not exists idx_blog_posts_slug on public.blog_posts (slug);
        alter table public.blog_posts
          drop constraint if exists blog_posts_scheduled_has_time,
          drop constraint if exists blog_posts_published_has_revision,
          drop constraint if exists blog_posts_slug_format,
          drop constraint if exists blog_posts_published_revision_fkey;
        drop table if exists public.blog_slug_redirects;
        drop table if exists public.blog_post_revisions;
        alter table public.blog_posts
          drop column if exists subtitle, drop column if exists slug_locked,
          drop column if exists content_html, drop column if exists content_text,
          drop column if exists content_schema_version, drop column if exists content_hash,
          drop column if exists word_count, drop column if exists block_count,
          drop column if exists cover_asset_id, drop column if exists og_asset_id,
          drop column if exists version, drop column if exists published_revision_id,
          drop column if exists last_published_at, drop column if exists schedule_error;
    """))

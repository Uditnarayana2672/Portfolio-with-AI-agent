-- Blog Manager schema (Blog Manager Plan.md §3). Additive only.
-- Apply in Supabase (SQL editor or `apply_migration` as "blog_manager").
-- Mirrored by alembic/versions/006_blog_manager.py.

-- 1. Archive timestamp ("archived 3d ago", sortable).
alter table public.blog_posts add column archived_at timestamptz;
update public.blog_posts set archived_at = updated_at where status = 'archived';
alter table public.blog_posts
  add constraint blog_posts_archived_has_time check ((status = 'archived') = (archived_at is not null));

-- 2. Weighted search vector: title A, subtitle/excerpt B, body C.
--    Generated + stored, so no write path has to maintain it.
alter table public.blog_posts add column search_vector tsvector generated always as (
  setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english'::regconfig, coalesce(subtitle, '') || ' ' || coalesce(excerpt, '')), 'B') ||
  setweight(to_tsvector('english'::regconfig, coalesce(content_text, '')), 'C')
) stored;
create index idx_blog_posts_search_vector on public.blog_posts using gin (search_vector);

-- 3. Default list order.
create index idx_blog_posts_status_updated on public.blog_posts (status, updated_at desc, id);

-- 4. Deleting a post must not fail because it has comments.
alter table public.comments drop constraint comments_blog_id_fkey,
  add constraint comments_blog_id_fkey
  foreign key (blog_id) references public.blog_posts(id) on delete cascade;

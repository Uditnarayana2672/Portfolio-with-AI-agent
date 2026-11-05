-- Blog editor schema (New Blog Post Plan.md §5).
-- Apply in Supabase (SQL editor or `apply_migration` as "blog_editor_schema").
-- Mirrored by alembic/versions/005_blog_editor_schema.py.

alter table public.blog_posts
  add column subtitle                text,
  add column slug_locked             boolean     not null default false,
  add column content_html            text        not null default '',
  add column content_text            text        not null default '',
  add column content_schema_version  integer     not null default 1,
  add column content_hash            text,
  add column word_count              integer     not null default 0,
  add column block_count             integer     not null default 0,
  add column cover_asset_id          uuid        references public.media_assets(id) on delete set null,
  add column og_asset_id             uuid        references public.media_assets(id) on delete set null,
  add column version                 integer     not null default 1,
  add column published_revision_id   uuid,
  add column last_published_at       timestamptz,
  add column schedule_error          text;

create table public.blog_post_revisions (
  id            uuid primary key default gen_random_uuid(),
  post_id       uuid not null references public.blog_posts(id) on delete cascade,
  kind          text not null check (kind in ('publish','manual','restore')),
  label         text check (char_length(label) <= 60),
  snapshot      jsonb not null,
  content_html  text  not null,
  content_hash  text  not null,
  word_count    integer not null default 0,
  created_by    uuid references public.users(id),
  created_at    timestamptz not null default now()
);
create index idx_blog_revisions_post on public.blog_post_revisions (post_id, created_at desc);

alter table public.blog_posts
  add constraint blog_posts_published_revision_fkey
  foreign key (published_revision_id) references public.blog_post_revisions(id) on delete set null;

create table public.blog_slug_redirects (
  old_slug    text primary key,
  post_id     uuid not null references public.blog_posts(id) on delete cascade,
  created_at  timestamptz not null default now()
);
create index idx_blog_slug_redirects_post on public.blog_slug_redirects (post_id);

alter table public.blog_posts
  add constraint blog_posts_scheduled_has_time
    check ((status = 'scheduled') = (scheduled_at is not null)),
  add constraint blog_posts_published_has_revision
    check (status <> 'published' or published_revision_id is not null),
  add constraint blog_posts_slug_format
    check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and char_length(slug) between 3 and 80);

alter table public.blog_posts drop constraint blog_posts_category_id_fkey,
  add constraint blog_posts_category_id_fkey
  foreign key (category_id) references public.blog_categories(id) on delete set null;

drop index if exists public.idx_blog_posts_search;
create index idx_blog_posts_search on public.blog_posts using gin (
  to_tsvector('english', coalesce(title,'') || ' ' || coalesce(subtitle,'') || ' ' ||
                         coalesce(excerpt,'') || ' ' || coalesce(content_text,'')));
create index idx_blog_posts_title_trgm on public.blog_posts using gin (title gin_trgm_ops);
create index idx_blog_posts_due on public.blog_posts (scheduled_at) where status = 'scheduled';
drop index if exists public.idx_blog_posts_slug;

alter table public.blog_categories add column sort_order integer not null default 0;
create unique index uq_blog_categories_name_ci on public.blog_categories (lower(name));
insert into public.blog_categories (name, slug, sort_order) values
  ('AI & Agents','ai-agents',1), ('Web Dev','web-dev',2), ('Tutorials','tutorials',3),
  ('Opinion','opinion',4), ('Career','career',5)
on conflict (slug) do nothing;

alter table public.blog_post_revisions enable row level security;
alter table public.blog_slug_redirects enable row level security;

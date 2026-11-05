-- Public site support (My prompts/End of Project Plan.md section 11). Additive only.
-- Apply in Supabase (`apply_migration` as "public_site").
-- Mirrored by alembic/versions/009_public_site.py.

-- 1. Safer default: a new user is never an admin by accident.
alter table public.users alter column role set default 'viewer';

-- 2. Polls attach to a project block; one vote per browser.
alter table public.polls add column if not exists block_id uuid unique
  references public.project_blocks(id) on delete cascade;
create unique index if not exists poll_votes_one_per_session on public.poll_votes (poll_id, session_id);

-- 3. Newsletter double opt-in.
alter type public.subscriber_status add value if not exists 'pending';
alter table public.newsletter_subscribers
  add column if not exists confirm_token text unique,
  add column if not exists confirm_expires_at timestamptz,
  add column if not exists confirmed_at timestamptz;

-- 4. One newsletter send per post.
create table if not exists public.newsletter_sends (
  post_id uuid primary key references public.blog_posts(id) on delete cascade,
  recipients integer not null,
  sent_at timestamptz not null default now()
);
alter table public.newsletter_sends enable row level security;

-- 5. Live site rebuild tracking.
create table if not exists public.site_builds (
  site text primary key check (site in ('portfolio', 'lighthouse')),
  dirty_since timestamptz,
  trigger_after timestamptz,
  last_triggered_at timestamptz,
  updated_at timestamptz not null default now()
);
alter table public.site_builds enable row level security;
insert into public.site_builds (site) values ('portfolio'), ('lighthouse') on conflict do nothing;

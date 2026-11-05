-- Turn on Row Level Security for every public table that had it off (Dashboard Overview Plan.md section 1).
-- No policies: the anon and authenticated roles lose direct table access. The backend connects as postgres
-- and is unaffected. Mirrored by alembic/versions/008_enable_rls.py.

alter table public.users enable row level security;
alter table public.blog_categories enable row level security;
alter table public.projects enable row level security;
alter table public.blog_posts enable row level security;
alter table public.media_assets enable row level security;
alter table public.reactions enable row level security;
alter table public.comments enable row level security;
alter table public.newsletter_subscribers enable row level security;
alter table public.contact_messages enable row level security;
alter table public.page_views enable row level security;
alter table public.activity_log enable row level security;
alter table public.admin_style_profile enable row level security;
alter table public.assistant_sessions enable row level security;
alter table public.assistant_messages enable row level security;
alter table public.visitor_graph_nodes enable row level security;
alter table public.visitor_graph_edges enable row level security;
alter table public.jerry_voice_profile enable row level security;
alter table public.jerry_style_corpus enable row level security;
alter table public.jerry_pricing_kb enable row level security;
alter table public.jerry_notes enable row level security;
alter table public.jerry_admin_sessions enable row level security;
alter table public.jerry_escalations enable row level security;
alter table public.jerry_bookings enable row level security;

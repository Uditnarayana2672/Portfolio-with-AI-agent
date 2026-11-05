# Dashboard Overview and Portfolio Info: Plan and API Spec

**Status: approved and built on 2026-11-05. Migrations 007 and 008 are applied to the live database. Final logged-in check is still to be done by Udit.**

Scope: the admin Overview page at `/dashboard`, with two parts:

1. **Command Deck**: real counts, recent activity and quick-create links.
2. **Portfolio Info**: an editor for the main portfolio page content, saved as one document. Pressing Save makes it live.

A public read API is included so the portfolio site can use this content later.

---

## 1. Database check

Checked on the live Supabase project `waddmljfjyushobocukr` with read-only queries on 2026-11-05.

### Current data

| Item | Live value |
|---|---|
| Projects | 4 (4 published) |
| Blog posts | 1 (1 published) |
| Media assets | 27 (26 images, 1 video) |
| Activity log rows | 119 |
| Admin users | 1 |

### Does the database have what we need?

| Need | Result | Action |
|---|---|---|
| Project counts by status | Yes | Reuse the existing API |
| Blog counts by status | Yes | Reuse the existing API |
| Media counts and storage | Yes | Reuse the existing API |
| Recent activity data | Yes, `activity_log` is being written | Add a read API; no table change |
| Portfolio content storage | **No**, no suitable table exists | **Add table `portfolio_content`** |
| Activity type for portfolio saves | **No**, not in the `activity_type` enum | **Add enum value `portfolio_updated`** |
| Keep content updated_at current | Yes, `set_updated_at()` exists | Reuse it |

### New database objects

These changes only add objects. No existing table or data changes.

```sql
alter type public.activity_type add value if not exists 'portfolio_updated';

create table public.portfolio_content (
  id          smallint primary key default 1 check (id = 1),  -- only one row can exist
  content     jsonb not null,
  version     integer not null default 1,                     -- stops one tab overwriting another
  updated_by  uuid references public.users(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create trigger portfolio_content_set_updated_at
  before update on public.portfolio_content
  for each row execute function public.set_updated_at();

-- No policies: only the backend can reach this table. The public read goes through the API.
alter table public.portfolio_content enable row level security;

-- Then one INSERT that seeds the row with the current site text (see "Content document" in section 3).
```

Files: `supabase/migrations/007_portfolio_content.sql` and a matching `alembic/versions/007_portfolio_content.py`.

The live database has no `alembic_version` table, and migrations 005 and 006 are missing from Supabase's migration history even though their tables exist. So I would apply 007 through Supabase as the earlier ones appear to have been, and leave that history as it is.

### Security problem found: needs your decision

**23 of the 30 public tables have Row Level Security turned off, and the `anon` role has select, insert and delete rights on the four I tested (`users`, `contact_messages`, `projects`, `activity_log`).** The anon key is sent to the browser for login, so anyone who has it can read or change those tables directly, bypassing your API. That includes `users` (with its `role` column) and `contact_messages`.

The fix looks safe for your app:

- The admin UI has no direct `supabase.from()` calls.
- The backend connects as `postgres`, and it already works with `project_blocks`, which has RLS on.
- The new-user trigger (`handle_new_auth_user`) runs as security definer.

It still changes the live database, so it is a separate approval. I would run the existing test suite and a live check afterwards.

```sql
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blog_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blog_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.newsletter_subscribers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.page_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_style_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visitor_graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visitor_graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_voice_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_style_corpus ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_pricing_kb ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_admin_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jerry_bookings ENABLE ROW LEVEL SECURITY;
```

---

## 2. API list

All paths start with `/api/v1`. Admin APIs need `Authorization: Bearer <Supabase token>` and return 401 or 403 otherwise.

| # | Method | Path | Used for | Status |
|---|---|---|---|---|
| 1 | GET | `/admin/projects/status-counts` | Projects tile | Exists |
| 2 | GET | `/admin/blogs/stats` | Blogs tile | Exists |
| 3 | GET | `/admin/media/stats` | Media tile | Exists |
| 4 | GET | `/admin/activity` | Activity stream | **New** |
| 5 | GET | `/admin/portfolio-content` | Load the editor | **New** |
| 6 | PUT | `/admin/portfolio-content` | Save the editor | **New** |
| 7 | GET | `/portfolio-content` | Public read | **New** |

I am not adding one combined dashboard API. The three stats APIs already exist, and calling them separately means one failed tile doesn't blank the whole page.

---

## 3. API details

### 3.1 GET `/admin/projects/status-counts` (exists)

Input: none. Output (current live values):

```json
{ "total": 4, "draft": 0, "published": 4, "archived": 0 }
```

### 3.2 GET `/admin/blogs/stats` (exists)

Input: none. Output (current live values shown; `created_this_month` is illustrative):

```json
{
  "total": 1,
  "published": 1,
  "draft": 0,
  "scheduled": 0,
  "archived": 0,
  "created_this_month": 1,
  "next_scheduled_at": null,
  "failed_schedules": 0
}
```

Two behaviours to know:

- Posts in `review` are counted as `draft`.
- Blog `total` leaves out archived posts, but project `total` includes them. The tiles will show each status separately so this doesn't mislead.

### 3.3 GET `/admin/media/stats` (exists)

Input: none. Output (values illustrative except the 26 / 1 / 27 counts):

```json
{
  "total_assets": 27,
  "added_today": 0,
  "counts": { "image": 26, "video": 1 },
  "storage": {
    "used_bytes": 1503238553,
    "quota_bytes": 2415919104,
    "used_human": "1.4 GB",
    "quota_human": "2.25 GB",
    "percent_used": 62,
    "plan": "PLUS"
  },
  "last_cleanup": null
}
```

The exact keys inside `counts` will be confirmed against the live response when building the tile.

### 3.4 GET `/admin/activity` (new)

Input (query):

| Param | Type | Default | Rule |
|---|---|---|---|
| `limit` | integer | 20 | 1 to 50 |

Output, newest first:

```json
{
  "items": [
    {
      "id": "6f1c1b5e-1111-4a2b-9c3d-000000000001",
      "action_type": "blog_updated",
      "category": "blog",
      "description": "Blog post 'Samsung S26 Ultra' updated.",
      "entity_type": "blog_post",
      "entity_id": "6f1c1b5e-2222-4a2b-9c3d-000000000002",
      "entity_title": "Samsung S26 Ultra",
      "actor": "you",
      "link": "/admin/blogs/6f1c1b5e-2222-4a2b-9c3d-000000000002/edit",
      "created_at": "2026-11-04T18:03:34Z"
    }
  ]
}
```

- `category`: `project`, `blog`, `media`, `portfolio` or `other`.
- `actor`: `you`, or `system` when no user performed the action (such as a failed schedule).
- `link`: `null` if the item has since been deleted, so the stream never opens a dead page. Media links go to `/admin/media`, portfolio entries have no link.

Errors: `422` if `limit` is out of range.

### 3.5 GET `/admin/portfolio-content` (new)

Input: none. Output:

```json
{
  "version": 1,
  "updated_at": "2026-11-05T12:00:00Z",
  "updated_by_name": "Udit Narayana",
  "content": { "...": "see the content document below" }
}
```

Errors: `404 CONTENT_NOT_FOUND` only if the seed row is missing.

### Content document (used by APIs 5, 6 and 7)

This is the full seed, using the current site text:

```json
{
  "hero": {
    "eyebrow": "Agentic AI Expert @ IBM · 2026",
    "headline": "I build AI\nthat reasons.",
    "headline_accent": "And ships.",
    "intro": "Udit Narayana — full-stack engineer and agentic-AI specialist. I’ve sold it, operated it, and now I build it, end to end.",
    "highlights": ["Agentic AI", "Full-stack products", "Now at IBM"],
    "currently_building": {
      "title": "Currently building Jerry",
      "subtitle": "A public AI assistant — live now",
      "url": null
    }
  },
  "about": {
    "statement": "Sales taught me to *listen*. Operations taught me to *deliver*. Engineering lets me do both — at scale.",
    "today": "Today I build *agentic AI*: systems that plan, retrieve, remember and act — and stay honest when they don’t know.",
    "stats": [
      { "id": "st1", "value": "4", "suffix": ".", "label": "roles across sales, ops and engineering" },
      { "id": "st2", "value": "40", "suffix": "%", "label": "less reporting time from ops dashboards at Flipkart" },
      { "id": "st3", "value": "1000", "suffix": "+", "label": "student conversations on career paths" },
      { "id": "st4", "value": "IBM", "suffix": "", "label": "Agentic AI Expert, since 2025" }
    ]
  },
  "what_i_do": {
    "title": "Curious full-stack engineer who wants AI to *actually work.*",
    "subtitle": "Agentic systems · Web products · APIs",
    "points": [
      { "id": "p1", "text": "Build *agentic AI systems* — LangGraph workflows with reasoning, tools, retrieval & persistent memory." },
      { "id": "p2", "text": "Ship *end-to-end web products* — React + Vite front ends on FastAPI & Postgres backends." },
      { "id": "p3", "text": "Design *clean, async APIs* other developers actually enjoy using." },
      { "id": "p4", "text": "Craft *micro-interactions and motion* that give products a sense of life." }
    ]
  },
  "skills": {
    "title": "What I’m fluent in.",
    "title_soft": "And how deep it runs.",
    "intro": "Pick a category. Bars show depth — the longer the bar, the more production miles."
  },
  "tech": [
    {
      "id": "t1",
      "name": "LangGraph",
      "logo_slug": "langchain",
      "categories": ["ai"],
      "level": "expert",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t2",
      "name": "RAG & pgvector",
      "logo_slug": null,
      "categories": ["ai"],
      "level": "expert",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t3",
      "name": "Docker",
      "logo_slug": "docker",
      "categories": ["backend", "cloud"],
      "level": "working",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    }
  ],
  "experience_section": {
    "title": "Sales floor to AI lab.",
    "title_soft": "An unusual route.",
    "intro": "It’s exactly why my agents solve business problems, not just benchmarks."
  },
  "experience": [
    {
      "id": "e1",
      "company": "IBM",
      "role": "Agentic AI Expert",
      "start_year": 2025,
      "end_year": null,
      "summary": "Designing multi-agent systems for enterprise clients on watsonx + LangGraph.",
      "highlights": [
        "Multi-agent orchestration for enterprise workflows",
        "RAG pipelines grounded in client data, with citations"
      ]
    }
  ]
}
```

The `tech` and `experience` arrays above show examples. The seed will contain every item now on the site: all techs and all four jobs (IBM, Neudesic, Flipkart, Skillvertex).

**Rules checked on the server**

| Field | Rule |
|---|---|
| Text with `*word*` | `*...*` marks highlighted words. All text is shown as plain text, never as HTML |
| `id` | Short string, unique within its list. The editor creates it |
| `level` | `working`, `advanced` or `expert` (shown as bars of 55%, 80% and 95%) |
| `categories` | At least one of `ai`, `backend`, `frontend`, `cloud` |
| `logo_slug` | Lowercase letters, numbers and hyphens, or `null`. `null` or a missing logo shows the small letter badge |
| `end_year` | `null` means "Present"; otherwise not before `start_year` |
| `url` | `https://`, a site path, or `null` |
| Text lengths | Headlines 120, one-line fields 200, paragraphs 600 characters |
| List sizes | tech 60, experience 20, points 8, stats 6, highlights per job 8 |
| Whole document | 64 KB at most; unknown fields are rejected |

List order is display order, so reordering just changes the array.

### 3.6 PUT `/admin/portfolio-content` (new)

Input:

```json
{
  "version": 1,
  "content": { "...": "the full content document" }
}
```

Output (`200`):

```json
{
  "version": 2,
  "updated_at": "2026-11-05T12:30:00Z",
  "updated_by_name": "Udit Narayana",
  "changed_sections": ["hero", "tech"],
  "content": { "...": "the saved document" }
}
```

Save behaviour:

- The change is live as soon as this returns.
- It writes an activity entry, for example `Portfolio content updated: hero, tech.`
- If nothing changed, it returns `200` with the same version and writes no activity.

Errors, in the same format as the blog APIs:

```json
{
  "detail": {
    "error": "VERSION_CONFLICT",
    "message": "This content was changed somewhere else. Reload to get the latest version.",
    "detail": { "current_version": 3, "updated_at": "2026-11-05T12:29:00Z" }
  }
}
```

| Status | `error` | When |
|---|---|---|
| 409 | `VERSION_CONFLICT` | Saved from an out-of-date tab; nothing is overwritten |
| 422 | `INVALID_CONTENT` | A rule failed; `detail.fields` gives each path, such as `tech[3].level` |
| 413 | `CONTENT_TOO_LARGE` | Over 64 KB |

### 3.7 GET `/portfolio-content` (new, public)

Input: none, no login. Output:

```json
{
  "updated_at": "2026-11-05T12:30:00Z",
  "content": { "...": "the full content document" }
}
```

- Sends `Cache-Control: public, max-age=60`, so a save can take up to a minute to appear for visitors.
- It does not expose `version` or who edited.
- Connecting the redesign pages to this API is a later step, and the live site's domains must be added to `CORS_ALLOWED_ORIGINS` then.

---

## 4. Overview page

**Route:** replaces the placeholder at `/dashboard`. Login will now land here instead of Media.

### Command Deck

| Tile | Big number | Below it |
|---|---|---|
| Projects | Published count | Drafts, archived |
| Blog posts | Published count | Drafts, scheduled, archived; a warning if a schedule failed |
| Media | Total assets | Added today, images and videos |
| Storage | Percent used | Used of quota, plan |

- **Activity stream:** the latest 20 actions, with time, type and a link to the item.
- **Quick create:** New project, New blog post, Upload media.
- **Left out because there is no data yet:** Jerry chats, free users, subscribers, unread notes, comments queue, system health, polls.
- Each tile loads on its own, with a loading state, and shows a retry button if it fails.

### Portfolio Info

It sits below the Command Deck, with tabs:

| Tab | What you edit |
|---|---|
| Hero | Eyebrow, headline, highlighted line, intro, highlights, "Currently building" card |
| About | Statement, "Today I build" text, stats |
| What I do | Title, subtitle, points |
| Tech & skills | Section text; add, edit, remove and reorder techs; set each tech's level, categories and where it appears |
| Experience | Section text; add, edit, remove and reorder jobs |

- One sticky Save button for the whole document, showing "Unsaved changes" and the last-saved time.
- A warning before you leave the page with unsaved work.
- Up and down buttons for reordering, since no drag-and-drop library is installed.
- If a save hits `VERSION_CONFLICT`, your edits stay on screen with a Reload option.
- A small logo preview next to each tech as you type its slug.
- It uses the current admin's hand-drawn style and `MiniStat`, and works at phone width.

---

## 5. Build plan

### Step 1: Database (needs your approval below)

- Write migration 007 and apply it to the live database.
- Add `PORTFOLIO_UPDATED` to `ActivityType` and a `PortfolioContent` model in `orm/models.py`.

### Step 2: Backend, following the existing layers

| Layer | Files |
|---|---|
| Domain | `domain/entities/portfolio_content.py`, `domain/repositories/portfolio_content_repository.py`; add a `list_recent` method to `activity_log_repository.py` |
| Application | `application/use_cases/portfolio/` (get, update), `application/use_cases/activity/list_recent_activity.py`, DTOs |
| Infrastructure | `persistence/repositories/portfolio_content_repository.py`; update the activity repository |
| API | `schemas/portfolio.py`, `schemas/activity.py`, `endpoints/portfolio_content.py`, `endpoints/activity.py`; register in `router.py` and `providers.py` |

The version check happens inside the `UPDATE ... WHERE version = :expected` statement, so two saves can't both succeed.

### Step 3: Backend tests

- **Activity:** ordering, limit, `category`, `actor`, and `link` being `null` for deleted items.
- **Save:** success, no-change, version conflict, each validation rule, and the activity entry.
- **Access:** admin routes reject missing or non-admin tokens; the public route needs no login and hides `version`.
- Then the full existing `pytest` suite.

### Step 4: Admin UI

| Area | Files |
|---|---|
| API and types | `src/api/dashboardApi.ts`, `src/api/portfolioApi.ts`, `src/types/portfolio.ts` |
| Page | `src/pages/OverviewPage.tsx` and its CSS |
| Command Deck | `src/components/overview/` (tiles, `ActivityStream`, `QuickCreate`) |
| Editor | `src/components/portfolio/` (one component per tab, `SaveBar`) |
| Wiring | `App.tsx` route; `LoginPage.tsx` redirect; default `activeItem` usage in `Sidebar.tsx` |

### Step 5: Verification

- `pytest`, `npm run lint` and `npm run build`.
- Browser checks at desktop and phone width with API responses mocked, including failed tiles and a version conflict.
- A live call to the public API.

**What needs you:** I can't sign in as you, so the final real check is yours: log in, confirm the tiles match the numbers above (4 projects, 1 blog, 27 media), edit one line, save, and reload.

---

## 6. Not included

- Connecting the redesign pages to these APIs, and public project and blog APIs (next phase).
- The contact form and email.
- Draft mode or version history. Save goes live, and the activity log records which sections changed but not the old text, so a wrong save has to be fixed by editing again.
- Uploading your own tech logos. Techs use a logo slug or the letter badge.
- Adding new skill categories. The four are fixed.
- Education, section headings for Selected Work and Writing, the code card and the layout stay hardcoded.

---

## 7. Approval needed

1. **Build plan:** approve sections 2 to 5.
2. **Live database change:** apply migration 007 to `waddmljfjyushobocukr`. It only adds objects.
3. **Security fix:** enable RLS on the 23 tables (recommended). Separate from 1 and 2.

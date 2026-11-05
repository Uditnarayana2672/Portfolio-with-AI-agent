# New Blog Post — Build Plan

Nov 3, 2026 · Udit N. · Companion to **New Blog Post API.md**

This plan covers building the admin blog editor (`New Blog Post.html`) end to end:
- database changes against the live Supabase project `Portfolio-with-AI-agent` (`waddmljfjyushobocukr`),
- backend in the existing onion architecture,
- frontend in `Portfolio_UI`,
- scheduling,
- answers to every design question raised about the page.

The reader-facing blog page is a separate, later build. This plan makes sure the data and the rendered HTML are ready for it, and that the preview already shows the same output.

---

## 1. Scope

**In:** the editor page, its rail (status, category & tags, cover & excerpt, search & social, checklist), autosave, preview, revisions, publish, schedule and automatic publish, unpublish, discard changes, category creation, and media through the existing Media Manager APIs.

**Out (later builds):** the public blog page and blog index, Blog Manager's table and bulk actions, comments moderation, RSS/sitemap generation, the AI Content Assistant (✨ button, side panel, toolbar "AI assist" — hidden in this build), and scheduled updates to already-live posts.

**Supersedes:** the API and schema sections of `Blog Post Editor — API Spec & Build Prompt.md`. That document assumed new tables and a signed-upload flow. The live database and the Media Manager that's already built make several of those changes unnecessary (§2).

---

## 2. What the live database already has

Inspected directly from Supabase on Nov 3, 2026.

### 2.1 Relevant tables today

| Table | Columns that matter here | State |
| --- | --- | --- |
| `blog_posts` | `id, title, slug (unique), content jsonb, excerpt, category_id → blog_categories, tags text[] (GIN), status blog_status, visibility content_visibility, views, allow_comments, seo jsonb, author_id → users, scheduled_at, published_at, cover_image_url, og_image_url, read_time, created_at, updated_at` | 0 rows. Triggers: `set_updated_at`, `set_published_at` (sets `published_at` on first transition to published, only if null). Indexes on status, slug, category, tags, published_at, scheduled_at (partial), FTS over title + excerpt. |
| `blog_categories` | `id, name (unique), slug (unique), description, created_at` | **0 rows — must be seeded.** No `sort_order`. |
| `media_assets` | `id, cloudinary_url, public_id (unique), resource_type (image/video/raw), source_type (cloudinary/youtube), external_id (unique when set), format, width, height, file_size, file_name, folder, alt_text, thumbnail_url, video_title, video_duration_seconds, file_hash, is_orphan, uploaded_by` | ~20 rows, all in `projects/*` and `system/og-images`. Full Media Manager API exists. |
| `activity_log` | `action_type activity_type, description, entity_type, entity_id, entity_title, performed_by, metadata jsonb` | Enum **already includes** `blog_created, blog_updated, blog_published, blog_archived, blog_deleted, blog_scheduled, blog_unscheduled, blog_unpublished, blog_changes_discarded, blog_revision_restored, blog_schedule_failed`. No enum migration needed. |
| `comments`, `reactions`, `page_views` | FK / content_type references to blog posts | Untouched by this build; the reason drafts that were once published can't be hard-deleted. |
| `users` | `role user_role (admin/viewer), is_blocked` | Used by `get_current_admin`. |

Enums: `blog_status = draft, review, published, archived, scheduled` · `content_visibility = public, members_only, unlisted`.

### 2.2 Gaps the editor needs filled

| Need | Missing today |
| --- | --- |
| Subtitle | `subtitle` column |
| Manual slug vs auto slug | `slug_locked` |
| Server-rendered body for preview, SEO, search and word count | `content_html`, `content_text`, `word_count`, `block_count`, `content_schema_version` |
| Two-tab safety | `version` |
| "Edit a live post without changing it until Update" | `content_hash`, `published_revision_id`, `blog_post_revisions` table |
| Cover/OG chosen from the library by asset | `cover_asset_id`, `og_asset_id` (keep the URL columns — Media usage search depends on them) |
| Old URLs keep working after a slug change | `blog_slug_redirects` table |
| Schedule failure reason | `schedule_error`, `last_published_at` |
| Category order | `blog_categories.sort_order` + seed rows |
| Video uploads for blogs | `blog/videos` folder (code constant, not DB) |

### 2.3 Migrations are tracked in Supabase, not Alembic

`supabase_migrations.schema_migrations` has 10 entries, and there is no `alembic_version` table. The `alembic/versions/00x_*.py` files are mirrors. This build follows the same pattern: apply `blog_editor_schema` via Supabase migrations, and add `alembic/versions/005_blog_editor_schema.py` as the mirror.

### 2.4 ⚠ Security finding — fix before shipping the editor

**Row Level Security is disabled on 23 public tables, including `blog_posts`, `blog_categories`, `media_assets`, `users` and `activity_log`.** The frontend ships the Supabase anon key (`src/lib/supabaseClient.ts`). Anyone who copies that key from the browser can read and **modify or delete every row** through Supabase's REST API, bypassing FastAPI completely. That includes publishing, editing or deleting blog posts and changing user roles.

Recommended fix (not applied — your call). The backend connects with the database owner role, which bypasses RLS, so enabling RLS with **no policies** locks out only the anon/authenticated REST access:

```sql
alter table public.blog_posts            enable row level security;
alter table public.blog_categories       enable row level security;
alter table public.blog_post_revisions   enable row level security;  -- after §5
alter table public.blog_slug_redirects   enable row level security;  -- after §5
alter table public.media_assets          enable row level security;
alter table public.users                 enable row level security;
alter table public.activity_log          enable row level security;
-- …and the other 16 tables the Supabase advisor lists
```

Before running it, confirm that `DATABASE_URL` uses the `postgres` role (it bypasses RLS) and that the frontend reads nothing directly from these tables. Today the frontend only uses Supabase for auth, so this should be safe. Run it on a branch first if unsure.

---

## 3. Answers to the design questions

### 3.1 How does the website know "The trade-offs no one talks about" is a sub-heading and the text below it is content?

Every piece of text is stored inside a **typed block**, not as loose text. The editor (TipTap, built on ProseMirror) keeps the post as a tree:

```
doc
├── paragraph   "Jerry is Udit's AI-powered client representative…"
├── heading(2)  "The trade-offs no one talks about"
├── paragraph   "A 500M-parameter model fine-tuned on…"
└── callout     "Voice without reasoning is karaoke…"
```

You mark a line as a heading in any of these four ways:
- Type `## ` at the start of a line (H2) or `### ` (H3).
- Put the cursor on the line and click H2/H3 in the toolbar.
- Type `/` and choose "Section heading".
- Use Ctrl/⌘+Alt+2 or 3.

Pressing Enter at the end of a heading always starts a normal paragraph, which is the "content under it". The server stores this JSON and renders `<h2 id="the-trade-offs-no-one-talks-about">` and `<p>`. That gives search engines a real document outline and gives readers a clickable table of contents.

**H1 is removed from the toolbar.** The post title is the page's only H1. Body headings are H2 (sections), H3 (sub-sections) and H4 (rare).

### 3.2 What is the yellow box?

It's a **callout** (also called an admonition): a highlighted aside for a key takeaway, tip or warning that shouldn't be lost in the flow. It's stored as a `callout` block with:
- a `variant`: **note** (yellow, the one in the mock), info (blue), tip (green), warning (amber) or danger (red),
- an optional bold `title`,
- an `icon`,
- body paragraphs or lists.

You insert one with `/callout` or the ⚑ toolbar button. A small menu on the box changes the variant and icon.

### 3.3 Auto-numbered points, with text between them

There are two tools for the two situations. Neither stores a number; numbers are computed every time the post is rendered, so deleting or moving a point renumbers everything.

**a) Numbered sub-headings** — for "Three layers, no training" with *1. The voice profile*, *2. Style corpus*, *3. Conversational memory*, and paragraphs, code and tables between them:
- Choose "Numbered sub-heading" in `/`, or type `#. ` at the start of a line.
- Write the heading text **without** a number. The editor shows "1." in front of it as a non-editable label.
- Write anything below it: paragraphs, code, tables, images.
- The next numbered sub-heading under the same section shows "2.", and so on. A new section heading (H2) restarts at 1.
- Stored as `{"type": "heading", "attrs": {"level": 3, "numbered": true}}`. The number appears in the HTML and the table of contents.

**b) Numbered lists** — for short steps, like the Claude message box behaviour:
- Type `1. ` to start a list.
- **Enter** = next number.
- **Shift+Enter** = a new paragraph *inside the same point*, for an explanation under a pointer, without starting a new number.
- **Tab / Shift+Tab** = nest or un-nest. Nested levels show a, b, c then i, ii, iii.
- **Enter on an empty point** = leave the list.
- A list item can also hold code blocks, images and callouts.

Rule of thumb: if each point needs more than two short paragraphs, use numbered sub-headings. They also show in the table of contents and get their own link anchors.

### 3.4 Code snippets anywhere

`/code`, the `{ }` toolbar button, or typing ```` ``` ```` + Enter inserts a **code block** at the cursor. It has:
- a language picker (16 languages, from editor-config) and an optional filename,
- line numbers and highlighted lines,
- a copy button on the public page.

Syntax highlighting happens at render time (lowlight in the editor, the same grammar set on the server/public side). Inline code uses backticks or Ctrl/⌘+E. Code blocks are allowed inside list items and callouts too.

### 3.5 Tables — colours, size, add/delete rows and columns like Word

Inserting:
- `/table` or ▦ opens a **size picker grid**: hover to choose up to 10×10, or type exact rows × columns (up to 200 × 20).
- Header row is on by default.

Editing (a floating table menu appears when the cursor is in a table, plus a right-click menu):
- Insert row above / below, insert column left / right, delete row, delete column, delete table.
- Merge or split cells; toggle header row or header column.
- Tab moves to the next cell. Tab in the last cell adds a row, like Word.
- Drag column borders to resize.

**Colours from the site theme only:**
- header style (ink, paper-dark, accent, highlight),
- zebra stripes on/off,
- per-cell background from the 9-token palette (API §4.3),
- borders (grid / rows only / none),
- cell alignment.

Colours are stored as **token names**, so they follow any future theme or dark-mode change. On phones the table scrolls sideways inside its own box.

### 3.6 Image or a scrollable collection of images

- **Single image:** `/image` or 📷 opens the media picker with "Upload from device" and "Cloudinary library". Alt text is required; caption and size (normal / wide / full-bleed) are optional.
- **Gallery:** `/gallery` opens the same picker in multi-select (2–20 images).
  - On the page it's a horizontal strip: swipe on phones, ← → buttons on desktop, scroll-snap so each image lands cleanly, and a click opens a full-screen lightbox.
  - Images can be reordered by dragging inside the block.
  - Row height is small / medium / large.
  - Each image keeps its own alt and caption.

Images are served through Cloudinary with `f_auto,q_auto` and a `srcset`, so phones download small files.

### 3.7 Videos — Cloudinary upload or YouTube

`/video` or ▶ opens a picker with three tabs:
- **Upload** — goes to Cloudinary through the existing `POST /admin/media/upload` (folder `blog/videos`, up to 200 MB).
- **Library** — uploaded videos and previously added YouTube links.
- **YouTube link** — paste any youtube.com / youtu.be / Shorts URL. The existing `import-url` endpoint fetches the title, thumbnail and duration.

On the public page:
- **Cloudinary video** plays in a native player on the page (poster image, controls, no autoplay).
- **YouTube video** plays **on the page** in a privacy-friendly `youtube-nocookie.com` player. It loads only when the reader clicks the thumbnail, which keeps the page fast. A **"Watch on YouTube ↗"** link under it opens the video on YouTube for readers who prefer that.

### 3.8 Quotes with attribution

`/quote`, the `"` toolbar button, or typing `> ` creates a quote block with a separate **attribution** field ("— alpha tester, week 2"). It has an optional source link and a "pull quote" style (large, centred) for testimonials. It's stored as `blockquote` with an `attribution` attribute, and renders as `<figure><blockquote>…</blockquote><figcaption>— …</figcaption></figure>`, which is the correct markup for a quote with a source.

### 3.9 Text links to other pages

Select text and press Ctrl/⌘+K, or ⇗ in the toolbar, or paste a URL over selected text. The link popover:
- accepts any `https://` URL,
- has a search box over **your own posts, projects and this post's headings** (API endpoint 22), so internal links are a click away,
- has an "open in new tab" toggle.

Internal links remember the target's id, so they keep working if that post's slug changes later. Unsafe links (`javascript:`) are refused.

### 3.10 Ctrl+B

Selecting words and pressing **Ctrl/⌘+B** makes them **bold**. If you also want a yellow marker-pen effect, that's the separate **highlight** mark: Ctrl/⌘+Shift+H, or the highlighter in the selection bubble, with palette colours. Italic Ctrl/⌘+I, underline Ctrl/⌘+U, strike Ctrl/⌘+Shift+X, inline code Ctrl/⌘+E. A small formatting bubble also appears above any selection.

### 3.11 Everything from "/" or the toolbar, at the cursor

Both the **slash menu** and the **toolbar** insert at the cursor position. Both are built from the same block registry, so they always list the same blocks.
- Slash menu: type `/` at the start of a line (or after a space), filter by typing ("/tab" → Table), arrow keys + Enter.
- Toolbar: H2 H3 · B I U S · link, bullets, numbers, quote · inline code, code block, table, callout · image, gallery, video, embed · divider.
- Toolbar buttons show active state from the editor (e.g. B is lit when the cursor is in bold text).

### 3.12 Adding new features to the list later

The editor uses a **block registry**: one entry per block type. Adding a block means:
1. **Frontend:** one folder `blogBlocks/<name>/` with the TipTap node, its editor UI, the slash/toolbar entry (label, icon, keywords, group) and a public preview renderer. Register it in `registry.ts`.
2. **Backend:** one Pydantic schema for its attributes and one HTML render function, registered in `BLOG_NODE_REGISTRY`. This is the same pattern as `BLOCK_CONFIG_MODELS` for project blocks.
3. It appears automatically in the toolbar, slash menu, `editor-config` (API endpoint 1), server validation and the preview.

`content.schema_version` lets you change an existing block's shape later, with a small upgrade function per version. Old posts upgrade on load and nothing breaks.

### 3.13 Draft saved after each Enter; remove Visibility

**Autosave** triggers:
- immediately when you press **Enter** (a block finished),
- 1.5 s after you stop typing,
- when the editor loses focus or the tab is hidden,
- at least every 30 s while you keep typing.

Only one request runs at a time. Edits made during a save are merged into the next one. Offline edits are kept in the browser and retried. The indicator shows *Saving… / Saved · 12 s ago / Offline — retrying / Conflict*.

**Visibility is removed from the Publish panel.** The column stays in the database (it's shared with projects), and every post is saved as `public`. If you want unlisted posts later, it's one select box again and no migration.

The rail's Draft / Scheduled / Publish **segmented control becomes a read-only status display**. Actions stay on the publish bar, so the two can't contradict each other.

### 3.14 Categories and tags — how they help SEO

- **Category** (one per post) builds a topic hub: `/blog/category/ai-agents` lists all AI posts. Google understands sites with clear topic clusters and internal links between related pages better. The category also feeds:
  - breadcrumbs (Blog › AI & Agents › Post, shown in search results through `BreadcrumbList` structured data),
  - `article:section`,
  - "More in AI & Agents" links at the bottom of the post.
- **Tags** (0–8) are finer cross-links: "related posts", tag pages, `article:tag` and `keywords` in the `BlogPosting` structured data. They don't directly rank you (Google ignores meta keywords), but they create internal links and keep readers on the site, which helps indirectly.
- **Watch out for thin pages:** a tag page with 1 post is a weak page. The public build should `noindex` tag pages with fewer than 3 posts.
- You can create a category from the select ("+ New category"), and new tags just by typing them.

### 3.15 Cover image from Cloudinary or from your device

One field, two views: the big drop zone in the editor and the small thumbnail in the rail both edit the same `cover_asset_id`. Clicking either opens the media picker:
- **Upload from device:** drag-drop or browse. It goes to Cloudinary folder `blog/covers` through the existing upload API, which also de-duplicates identical files.
- **Cloudinary library:** browse or search everything already uploaded.

You'll see a warning if the cover is narrower than 1200 px. Covers are cropped to 16:9 for cards and 1200×630 for social cards automatically through Cloudinary transformations; the original isn't changed.

### 3.16 Search & social — what each field does

| Field | What it's for | If left empty |
| --- | --- | --- |
| Meta title | The blue link text in Google results and the browser tab. Aim for 30–60 chars. | `"{Title} · Udit N."` |
| Meta description | The grey snippet under the link in Google. Aim for 120–160 chars. Google may rewrite it, but a good one raises clicks. | The excerpt |
| Canonical URL | See §3.17. | This post's own URL |
| OpenGraph image | See §3.18. | The cover image |
| Preview | Live mock of the Google result and the social share card, built from the fields above. | — |

The meters turn green inside the ideal range and amber outside it. Amber is a warning only; it never blocks publishing.

### 3.17 What is a canonical URL?

It tells search engines **"this is the original, official address of this article."** The same article can be reachable at several URLs:
- `…/blog/post`
- `…/blog/post?utm_source=linkedin`
- `…/blog/post/`
- a copy you cross-posted to Medium or dev.to

Without a canonical, Google may split ranking signals between them, or pick the Medium copy as the original. Every post automatically declares itself as canonical, so you normally **leave this field empty**. You only fill it in the rare case where this post is the copy and the original lives elsewhere. The common case is the reverse: when you cross-post *to* Medium, set Medium's canonical to point back to your site.

### 3.18 Why an OpenGraph image?

It's the picture that appears when someone shares your link on LinkedIn, X, WhatsApp, Slack or Discord. Posts with a proper 1200×630 image get noticeably more clicks than a bare link. These platforms read the `og:image` tag from the page's HTML **without running JavaScript** (see §3.20). If you don't upload a dedicated one, the cover is cropped to 1200×630 and used. A dedicated OG image is worth it when the cover has no text and you want the title baked into the share card.

### 3.19 Preview, like Projects

Same pattern as `/admin/projects/:id/preview`:
- **⌕ Preview** saves first, then opens `/admin/blogs/{id}/preview` in a new tab.
- That page renders the post with the **public post template**, using exactly the HTML the server will serve to readers (API endpoint 13).
- It has a desktop/mobile toggle, the Google result preview, the social card preview, the checklist and a Publish button.
- For a live post with unsaved changes, a "Live / With your changes" toggle compares them.

Until the public blog page is designed, the preview uses a simple temporary article template. When we design the reader page, the preview switches to it automatically, because both read the same payload.

### 3.20 Is a React page good for search?

**For the admin editor, it doesn't matter.** Admin pages should never be indexed.

**For the public blog pages, plain client-side React is a real weakness.**
- Google does run JavaScript, but in a delayed second pass, so new posts get indexed slower and less reliably.
- **Social networks don't run JavaScript at all**, so a client-rendered page shares with no title, description or image — the OG work in §3.18 would be wasted.
- Bing, DuckDuckGo and AI crawlers are also weaker at JavaScript.

### 3.21 Should we change the whole codebase?

**No.** FastAPI + React is a good stack, and the admin side (Media, Projects, now Blog) is the bulk of the work. Rewriting it would cost weeks and gain nothing for the admin. What matters is how the **public** pages are delivered, and this plan already prepares for that:
- The server renders `content_html`, the table of contents, all meta tags and JSON-LD on every save (API §3.7). The SEO-critical HTML exists before any browser runs.
- When we build the public blog face, pick one:
  1. **FastAPI serves `/blog/*` as server-rendered HTML** (Jinja template + `content_html` + meta tags), with small scripts for the gallery, code copy and video. Least new tech, best fit for a portfolio. **Recommended.**
  2. Prerender public routes at build/publish time (Vite SSG) — fine for posts, awkward for instant publishing and scheduling.
  3. A separate Next.js or Astro app for the public site only — the strongest option if the public site grows beyond a blog, but it adds a second frontend.

Decide this when designing the reader-facing page. Nothing in this build depends on the choice.

### 3.22 Scheduling and publishing

- **Publish:** runs the checklist. If every blocker is green, the post goes live immediately and its status becomes **Published**. If a blocker fails, the checklist panel opens at the problem. Warnings (amber) ask for a confirm but don't block.
- **Schedule:** pick a date and time in IST. The checklist must pass now (so you find out today). At the chosen minute the post publishes **automatically** (status → Published) — if the blockers are still green. If something broke in between (e.g. an image deleted), it goes back to Draft with a red "Scheduled publish failed: …" banner and an activity entry. Details in §7.
- **Once live**, the Publish button reads **Update**: edits autosave to a working copy, the public page keeps showing the last published version, and Update makes the changes live. The ⋯ menu adds Discard changes and Unpublish.

---

## 4. Architecture

### 4.1 Content model

- **Source of truth:** TipTap JSON in `blog_posts.content` (the column already exists and is jsonb). The browser never sends HTML.
- **Server render on every save:** allowlist validation → `content_html` (sanitized, heading ids, auto numbers, lazy images, `srcset`, escaped code), `content_text` (search and word count), TOC, stats, `content_hash`.
- **Live vs working copy:** the row is the working copy. The public page and `source=live` preview read `blog_post_revisions` via `published_revision_id`. Autosaving a live post never changes what readers see.

### 4.2 Request flow (autosave)

```
Editor (TipTap)  ──Enter / 1.5 s idle──▶  useAutosave queue (1 in flight, merge, retry, localStorage mirror)
   PATCH /admin/blogs/{id} {version, …changed fields}
      → endpoints/blogs.py            thin controller, error mapping
      → providers.get_update_blog_post
      → use_cases/blog/update_post.py  validate → render → slug → hash → checklist
           ├─ BlogContentRenderer port  → infrastructure/rendering/tiptap_renderer.py
           ├─ BlogPostRepository port   → SqlAlchemyBlogPostRepository (UPDATE … WHERE version = :v)
           └─ MediaAssetRepository      → asset existence / URL for cover & images
      ← PostSaveResult
```

### 4.3 Block registry (one list, used everywhere)

| Layer | File | Holds |
| --- | --- | --- |
| Backend domain | `app/domain/blog/content_schema.py` | Node/mark names, limits, palette tokens, schema version. No framework imports. |
| Backend API schemas | `app/api/v1/schemas/blog_nodes.py` | `BLOG_NODE_REGISTRY = {"callout": CalloutAttrs, …}` — Pydantic models per node, like `BLOCK_CONFIG_MODELS`. |
| Backend renderer | `app/infrastructure/rendering/tiptap_renderer.py` | One render function per node; unknown node → `InvalidContentError`. |
| Editor config | `GetEditorConfig` use case | Builds API endpoint 1 from the registry + settings. |
| Frontend | `Portfolio_UI/src/components/blog/editor/blocks/registry.ts` | One entry per block: TipTap extension, toolbar/slash metadata, insert command, NodeView. Filtered by `editor-config.blocks[].enabled`. |

### 4.4 Schema versioning

`content.schema_version` starts at 1. A breaking change to a node adds `upgrade_v1_to_v2(doc)` in `content_schema.py`. GET upgrades in memory, and the next PATCH persists the upgrade. Revisions keep their original version and are upgraded when viewed or restored.

---

## 5. Database migration — `blog_editor_schema`

Proposed — not yet applied. Apply via Supabase migrations and mirror in `alembic/versions/005_blog_editor_schema.py`.

```sql
-- 1. blog_posts: working-copy fields
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
-- Kept: cover_image_url / og_image_url (denormalized URL; Media usage search matches public_id in them),
--       read_time (used as reading_time_min), visibility (forced to 'public' by the API).

-- 2. Revisions
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

-- 3. Slug redirects
create table public.blog_slug_redirects (
  old_slug    text primary key,
  post_id     uuid not null references public.blog_posts(id) on delete cascade,
  created_at  timestamptz not null default now()
);
create index idx_blog_slug_redirects_post on public.blog_slug_redirects (post_id);

-- 4. Integrity
alter table public.blog_posts
  add constraint blog_posts_scheduled_has_time
    check ((status = 'scheduled') = (scheduled_at is not null)),
  add constraint blog_posts_published_has_revision
    check (status <> 'published' or published_revision_id is not null),
  add constraint blog_posts_slug_format
    check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and char_length(slug) between 3 and 80);

-- Category FK: allow delete → null (Blog Manager blocks it while in use anyway)
alter table public.blog_posts drop constraint blog_posts_category_id_fkey,
  add constraint blog_posts_category_id_fkey
  foreign key (category_id) references public.blog_categories(id) on delete set null;

-- 5. Indexes
drop index if exists public.idx_blog_posts_search;
create index idx_blog_posts_search on public.blog_posts using gin (
  to_tsvector('english', coalesce(title,'') || ' ' || coalesce(subtitle,'') || ' ' ||
                         coalesce(excerpt,'') || ' ' || coalesce(content_text,'')));
create index idx_blog_posts_title_trgm on public.blog_posts using gin (title gin_trgm_ops);  -- link-targets
create index idx_blog_posts_due on public.blog_posts (scheduled_at) where status = 'scheduled';  -- scheduler
drop index if exists public.idx_blog_posts_slug;  -- duplicate of the unique constraint's index

-- 6. Categories
alter table public.blog_categories add column sort_order integer not null default 0;
create unique index uq_blog_categories_name_ci on public.blog_categories (lower(name));
insert into public.blog_categories (name, slug, sort_order) values
  ('AI & Agents','ai-agents',1), ('Web Dev','web-dev',2), ('Tutorials','tutorials',3),
  ('Opinion','opinion',4), ('Career','career',5)
on conflict (slug) do nothing;

-- 7. RLS on the new tables (see §2.4 for the existing ones)
alter table public.blog_post_revisions enable row level security;
alter table public.blog_slug_redirects enable row level security;
```

Notes:
- The `blog_posts_slug_format` check is safe today because the table has 0 rows. If rows exist when this runs, normalize them first.
- `set_published_at` already does the right thing (first publish only). The publish service sets `published_at` explicitly for scheduled posts (= `scheduled_at`); the trigger leaves non-null values alone.

---

## 6. Backend build (FastAPI, onion layers)

### 6.1 Files

| Layer | New files |
| --- | --- |
| Domain | `domain/entities/blog_post.py` (BlogPost, BlogRevision, Checklist, ChecklistItem), `domain/blog/content_schema.py`, `domain/blog/checklist_rules.py` (pure functions, one per key), `domain/blog/slug.py`, `domain/repositories/blog_post_repository.py`, `blog_revision_repository.py`, `blog_category_repository.py`, `blog_redirect_repository.py`; new exceptions in `domain/exceptions.py`: `VersionConflictError`, `ChecklistFailedError`, `InvalidContentError`, `InvalidStateError(code)`, `SlugTakenError`, `ReservedSlugError` |
| Application | `application/interfaces/blog_content_renderer.py`, `embed_resolver.py`, `clock.py`; `application/dtos/blog.py`; `application/use_cases/blog/`: `get_editor_config`, `create_post`, `get_post`, `update_post`, `delete_post`, `check_slug`, `get_checklist`, `publish_post` (shared by endpoint 8 and the scheduler), `schedule_post`, `unschedule_post`, `unpublish_post`, `discard_changes`, `get_preview`, `create_revision`, `list_revisions`, `get_revision`, `restore_revision`, `list_categories`, `create_category`, `list_tags`, `resolve_embed`, `search_link_targets`, `publish_due_posts` |
| Infrastructure | ORM additions in `persistence/orm/models.py` (`BlogPostRevisions`, `BlogSlugRedirects`, new columns); `persistence/repositories/blog_*_repository.py`; `rendering/tiptap_renderer.py` (+ `pygments` for code highlighting into class names); `external/embed_resolver.py` (pattern rules + oEmbed through `safe_url_fetcher`); `scheduling/scheduler.py` (APScheduler `BackgroundScheduler`, 60 s interval) |
| API | `api/v1/endpoints/blogs.py` (1–17, 21, 22), `blog_taxonomy.py` (18–20), `internal_blogs.py` (23); `api/v1/schemas/blog.py`, `blog_nodes.py`; providers in `dependencies/providers.py`; `dependencies/cron.py` (`X-Cron-Secret`); register in `router.py` |

### 6.2 Cross-cutting rules (implement once)

- **Version check** in the repository's `update(…, expected_version)`. Raises `VersionConflictError(current_version, updated_at)`.
- **Single checklist** in `domain/blog/checklist_rules.py`. Used by GET checklist, PATCH response, preview, publish, schedule and the scheduler. Mirrored in TypeScript for live ticks; a test compares both against the same fixtures.
- **Activity log** through the existing `ActivityLogRepository`, using the existing enum values (`blog_created`, `blog_updated`, `blog_published`, `blog_scheduled`, `blog_unscheduled`, `blog_unpublished`, `blog_changes_discarded`, `blog_revision_restored`, `blog_schedule_failed`, `blog_deleted`). Autosaves do **not** log; only lifecycle actions do, so the dashboard feed stays readable.
- **Errors** use the `{"detail": {"error", "message", "detail"}}` envelope already used by projects.
- **Settings** (`infrastructure/config.py`): `SITE_URL`, `ADMIN_TIMEZONE=Asia/Kolkata`, `BLOG_CRON_SECRET`, `BLOG_SCHEDULER_ENABLED=true`.

### 6.3 Changes to existing code

- `application/dtos/media.py` → add `"blog/videos"` to `ALLOWED_FOLDERS`.
- `persistence/repositories/media_asset_repository.py::find_usage` → also scan `blog_post_revisions.snapshot` of **published** revisions (`location="live revision"`), so an asset used only by the live version can't be deleted.
- `requirements.txt` → `apscheduler`, `python-slugify`, `pygments`, `nh3` (defence-in-depth HTML sanitizing of the renderer's output).

---

## 7. Scheduling — making "publish at 9:00" reliable

1. **In-process job** — APScheduler in `app/main.py` lifespan, every 60 s, calls the `PublishDuePosts` use case.
2. **External trigger** — the same use case is exposed at `POST /internal/blogs/publish-due` (secret header). If the backend runs on a host that sleeps when idle (Render free tier and similar), the in-process timer never fires. A Supabase `pg_cron` job (enable the `pg_cron` and `pg_net` extensions) calls the endpoint every minute:
   ```sql
   select cron.schedule('blog-publish-due', '* * * * *', $$
     select net.http_post(
       url := 'https://<api-host>/api/v1/internal/blogs/publish-due',
       headers := jsonb_build_object('X-Cron-Secret', '<from vault>')
     ) $$);
   ```
   Store the secret in Supabase Vault (already installed), not inline.
3. **Exactly once** — `FOR UPDATE SKIP LOCKED` + the publish transaction means overlapping runs never double-publish.
4. **Late runs** — anything with `scheduled_at <= now()` publishes on the next run with `published_at = scheduled_at`.
5. **Failures** — checklist fails at fire time → back to draft, `schedule_error`, activity `blog_schedule_failed`. The editor shows the reason on next open.

Worst-case delay: about 60 s after the chosen minute.

---

## 8. Frontend build (`Portfolio_UI`)

### 8.1 Libraries

| Package | Why |
| --- | --- |
| `@tiptap/react`, `@tiptap/pm`, `@tiptap/starter-kit` (v3, React 19 compatible) | Editor core: paragraphs, headings, lists, quote, code, marks, undo |
| `@tiptap/extension-table` (+ row, cell, header), `-link`, `-underline`, `-highlight`, `-placeholder`, `-character-count`, `-code-block-lowlight`, `-typography`, `@tiptap/suggestion` | Tables, links, marks, placeholder, word count, highlighted code, smart quotes, slash menu |
| `lowlight` | Code highlighting in the editor |
| Custom nodes (in repo) | `callout`, `numberedHeading` (heading attr + NodeView label), `blogImage`, `imageGallery`, `video`, `embed`, `quoteWithAttribution` |

No other new dependencies. Media picker, chips, toggles and upload zone are reused from Media and Projects components.

### 8.2 Routes (`App.tsx`)

| Path | Page |
| --- | --- |
| `/admin/blogs` | Blog Manager placeholder with "+ New post" (replaces the `/blog` placeholder; `/blog` redirects) |
| `/admin/blogs/new` | `BlogEditorPage` (no id yet; lazy create) |
| `/admin/blogs/:id/edit` | `BlogEditorPage` |
| `/admin/blogs/:id/preview` | `BlogPreviewPage` |

### 8.3 Files

```
src/api/blogApi.ts                         typed client for endpoints 1–22 (axios, 401 → refresh → retry once)
src/types/blog.ts                          PostDetail, PostWritable, Checklist, … (mirrors API §3)
src/store/blogEditorStore.ts               zustand: post, version, saveState, dirtyFields, checklist, config
src/hooks/useAutosave.ts                   Enter / idle / blur / interval triggers, queue, merge, backoff, localStorage mirror, keepalive flush
src/hooks/useEditorConfig.ts
src/lib/blogChecklist.ts                   client copy of checklist rules
src/pages/BlogEditorPage.tsx (+ .module.css)
src/pages/BlogPreviewPage.tsx
src/components/blog/PublishBar.tsx         status pill, save indicator, Preview, Save draft, Schedule popover, Publish/Update, ⋯ menu
src/components/blog/TitleBlock.tsx         title, subtitle, slug line with slug-check
src/components/blog/CoverZone.tsx
src/components/blog/MediaPickerModal.tsx   Upload / Library / YouTube tabs; single and multi select
src/components/blog/editor/BlogEditor.tsx  TipTap instance + BubbleMenu + TableMenu
src/components/blog/editor/Toolbar.tsx
src/components/blog/editor/SlashMenu.tsx
src/components/blog/editor/TableSizePicker.tsx, TableMenu.tsx, ColorTokenPicker.tsx
src/components/blog/editor/LinkPopover.tsx
src/components/blog/editor/blocks/registry.ts + one folder per custom block
src/components/blog/rail/StatusPanel.tsx, TaxonomyPanel.tsx, CardPreviewPanel.tsx, SeoPanel.tsx, ChecklistPanel.tsx
src/components/blog/HistoryDrawer.tsx      revisions list / view / restore
src/components/blog/ConflictBanner.tsx, ScheduleFailedBanner.tsx
```

### 8.4 Keyboard shortcuts (shown in a "?" help popover)

| Keys | Action |
| --- | --- |
| `/` | Block menu |
| `## ` · `### ` · `#. ` | H2 · H3 · numbered sub-heading |
| `- ` · `1. ` · `> ` · ```` ``` ```` · `---` | Bullets · numbered list · quote · code block · divider |
| Enter · Shift+Enter | Next block / next number · new line in the same block or point |
| Tab · Shift+Tab | Nest / un-nest list item; next / previous table cell |
| ⌘/Ctrl + B I U E K | Bold, italic, underline, inline code, link |
| ⌘/Ctrl+Shift+H · ⌘/Ctrl+Shift+X | Highlight · strike |
| ⌘/Ctrl+S | Save draft (revision) |
| ⌘/Ctrl+Z · ⌘/Ctrl+Shift+Z | Undo / redo |

---

## 9. Cross-cutting edge cases

The per-endpoint matrix is in API §9. The ones that shape the whole build:

1. **Never lose text:** in-memory queue + `localStorage` mirror + keepalive flush + conflict banner instead of overwrite.
2. **Live page isolation:** readers only ever see a publish revision.
3. **Media integrity:** usage scanning covers working copy, cover/OG and live revision; the checklist re-verifies assets at publish and at scheduled time.
4. **Safe HTML:** allowlist on input, escaping in the renderer, `nh3` on output, sandboxed iframes only for server-built embed URLs, no `javascript:` links.
5. **Time:** UTC in the DB, explicit offsets in requests, IST in the UI.

---

## 10. Build order and done criteria

| Step | Deliverable | Test |
| --- | --- | --- |
| 0 | Decide on RLS (§2.4) and apply it on a branch | Supabase advisor shows no `rls_disabled` for blog/media/users tables; backend still works |
| 1 | Migration `blog_editor_schema` + Alembic mirror + ORM models | Migration applies cleanly; categories seeded |
| 2 | Domain: content schema, checklist rules, slug | pytest: each rule, slug transliteration, reserved words |
| 3 | Renderer | pytest: every node and mark → HTML; unknown node → 422; `javascript:` link rejected; code escaping; numbering; heading id de-dup |
| 4 | Endpoints 1–6, 18–20 | pytest + httpx: create/idempotency, PATCH version conflict, slug clash/suggestion, category create conflict, tag normalization |
| 5 | Endpoints 7–12, 14–17 | publish blocked by checklist; publish → edit → `has_unpublished_changes` → Update / Discard; unpublish; revisions prune at 50; restore keeps a "before restore" copy |
| 6 | Endpoints 21–23 + scheduler + media folder/usage changes | scheduler publishes a due post once under two concurrent runs; failing checklist → draft + activity; usage finds live-revision assets |
| 7 | Frontend: API client, store, autosave hook | vitest: debounce, Enter trigger, queue/merge, retry, recovery |
| 8 | Editor UI: toolbar, slash menu, all blocks, table menu, media picker | Manual + Playwright: build the sample post from the HTML mock end to end |
| 9 | Rail, checklist, publish bar, schedule popover, history drawer | vitest: client checklist matches server fixtures |
| 10 | Preview page | Visual check desktop/mobile; Google + social previews |

**Done means:** you can click "+ New post" and write the "Building Jerry" post exactly as in the mock, including:
- headings and numbered sub-headings with text between them,
- a yellow callout, a code block,
- a coloured table with a row and a column added and deleted,
- a gallery, a YouTube video and an uploaded video,
- a quote with attribution, internal and external links, bold and highlight.

From there you can:
- see autosave after each Enter, and open it in two tabs and get the conflict banner,
- preview it, schedule it 5 minutes ahead and watch it publish itself,
- edit it, see "unpublished changes", and Update it.

Throughout, `pytest`, `vitest`, `ruff` and `eslint` pass.

---

## 11. Open questions

1. **Public blog delivery** (§3.21): FastAPI server-rendered pages (recommended) vs Next/Astro. Needed before the reader-facing build, not before this one.
2. **Scheduled updates to live posts** ("publish these edits at 9 AM"): left out of v1. Today, scheduling is for posts that aren't live yet.
3. **AI Content Assistant** in the mock: hidden in this build. When it's added, it reads the same `content` JSON and returns suggestions as JSON patches the editor can accept, so it fits the registry without new storage.
4. **Where is the backend hosted?** `docker-compose.yml` is empty. If it's a host that sleeps, the `pg_cron` trigger in §7 is required, not optional.

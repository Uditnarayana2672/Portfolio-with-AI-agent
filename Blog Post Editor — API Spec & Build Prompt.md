# Blog Post Editor — API Spec & Build Prompt

Nov 3, 2026 · @UDIT NARAYANA

## Decisions and scope

This build ships the Blog Post Editor end to end (FastAPI + Postgres + React), plus a stub Blog Manager page whose only job is an **Add new post** button. Blog Manager and Dashboard Overview follow in that order; their endpoints are sketched in the look-ahead section so the editor's data model already fits them.

| Decision | Choice | Consequence for the API |
| --- | --- | --- |
| Content format | TipTap JSON is the source of truth | Client sends `content_json` only. The backend renders sanitized HTML from a fixed node allowlist, so the browser never sends HTML. |
| AI assist | Left out of this build | The toolbar "AI assist" button, the floating button and the side panel are not rendered. No `/admin/ai/*` calls. |
| Image uploads | Signed direct upload to Cloudinary | Backend signs, browser uploads straight to Cloudinary, then registers the asset. Files never pass through Render. |
| Revisions | Snapshot on publish and on manual Save draft | Autosave overwrites the working copy. The published version is itself a revision, so editing a live post never changes the public page until you press Update. |

Three design changes I'm proposing to the editor mock, each explained in the audit below:

- **Drop H1 from the toolbar.** The post title is already the page's H1; body headings should be H2 and H3 only.
- **Make the rail's status control read-only.** The segmented Draft / Scheduled / Publish control duplicates the Schedule and Publish buttons and can contradict them.
- **One cover-image field, two views.** The large drop zone and the rail thumbnail edit the same `cover_asset_id`.

## Feature audit — every control in New Blog Post.html

Every control maps to either a client-only behaviour or one endpoint; nothing on the page needs an endpoint that isn't listed in the API section. The "Endpoint" column uses short names defined there.

### Publish bar (sticky top)

| Control | How it should work | Endpoint |
| --- | --- | --- |
| Status pill ("○ Draft") | Read-only. Shows Draft, Scheduled · \<date>, Published, or Published · unpublished changes. Derived from `status` and `has_unpublished_changes`. | from GET post |
| Autosave indicator | States: Saving… / Saved · 12 sec ago / Offline, retrying / Conflict. Debounce 1.5 s after the last keystroke, force a save every 30 s while typing. | PATCH post |
| Preview | Flushes any pending autosave, then opens `/admin/blogs/:id/preview` in a new tab, rendering the server's `content_html` in the public post template. Admin-only, no share token in v1. | PATCH post, GET post |
| Save draft | Flushes autosave, then writes a manual revision snapshot. Toast "Draft saved". Also bound to ⌘S / Ctrl+S. | PATCH post, POST revision |
| Schedule | Opens a date-time popover (admin's timezone, IST). Runs the publish checklist first; blockers stop it. Must be at least 5 min ahead. When already scheduled, the button reads "Reschedule" and the popover offers "Unschedule". | POST schedule, DELETE schedule |
| Publish | Runs the checklist; blockers open the checklist panel. On success, snapshots a publish revision, makes it live, shows the public URL. Once live the button reads **Update** (publishes working-copy changes) and a ⋯ menu adds Discard changes and Unpublish. | POST publish, POST discard-changes, POST unpublish |

### Title block

| Control | How it should work | Endpoint |
| --- | --- | --- |
| Title input | Required to publish, 10–100 chars. Autosaves. Drives the slug until the slug is edited by hand. | PATCH post |
| Subtitle input | Optional, max 160 chars. Shown under the title on the public post. | PATCH post |
| Slug line + "✎ edit" | Auto-slug from title (lowercase, a–z 0–9 hyphens, 3–80 chars) while `slug_locked` is false. Clicking edit locks it. Availability is checked as you type (debounced 400 ms) and suggests `-2` on clash. Changing the slug of a published post records a 301 redirect from the old one. | GET slug-availability, PATCH post |

### Cover image

| Control | How it should work | Endpoint |
| --- | --- | --- |
| Drop zone / "browse Cloudinary library" | Drag-drop or pick file → sign → upload directly to Cloudinary → register asset → set `cover_asset_id`. "Browse library" opens a modal over the `/blogs` folder. jpg, png, webp only, max 10 MB, min 1200 px wide. Alt text is asked for at upload. | POST sign-upload, POST media, GET media, PATCH post |
| Rail "Card preview → cover" thumbnail | Same field as the drop zone (proposal: one field, two views). Click opens the same picker. | same as above |

### Toolbar and body

| Control | How it should work | Endpoint |
| --- | --- | --- |
| H1 / H2 / H3 | Proposal: remove H1 (the title is the page H1). H2 and H3 feed the public table of contents. | client only |
| B / I / U / S | TipTap marks. Underline is kept but discouraged on the web (it reads as a link). | client only |
| Link (⇗) | Popover with URL + "open in new tab". Allowed schemes: https, http, mailto, relative `/…`. External links render with `rel="noopener nofollow"`. | client only |
| Bullet / numbered list, Quote | TipTap nodes. | client only |
| Inline code, Code block | Code block has a language picker (python, typescript, javascript, bash, sql, json, yaml, html, css, plaintext). Public page highlights at render time. | client only |
| Table | Insert 3×3 with header row; add/remove rows and columns from a cell menu. | client only |
| Callout (⚑) | Custom node with variant info / tip / warning / danger, an optional bold title and a body. | client only |
| Image (📷) | Same upload flow as the cover, inserts an image node with `asset_id`, `alt` (required), optional caption. | POST sign-upload, POST media |
| Video (▶) | Paste a YouTube, Vimeo or Cloudinary video URL; the server normalizes it to an embed URL. | POST embeds/resolve |
| Embed (⎘) | Paste a CodePen, CodeSandbox, Figma, GitHub Gist or YouTube URL; anything else is refused. | POST embeds/resolve |
| AI assist | Removed in this build. | — |
| "/" slash menu | Same commands as the toolbar, keyboard-driven. | client only |
| Word count footer | Words, reading time (230 words/min, rounded up), block count, last edit time. Shown live from the editor, then corrected by the server's figures after each save. | from PATCH post |

### Right rail

| Control | How it should work | Endpoint |
| --- | --- | --- |
| Status segmented control | Proposal: read-only display of the current state, with the scheduled date. Actions stay on the publish bar. | from GET post |
| Scheduled at | Shown only when scheduled; clicking opens the Schedule popover. Stored as UTC, displayed in the admin's timezone. | POST schedule |
| Visibility | Public, Members only (logged-in users), Unlisted (reachable by link, excluded from listings, sitemap and RSS, `noindex`). New column, not in the spec. | PATCH post |
| Category | Single select, required to publish. Loaded from the categories endpoint. | GET categories, PATCH post |
| Tags | Chips with autocomplete from existing tags. Normalized to lowercase kebab-case, 1–8 tags, each 2–30 chars. Enter or comma adds, × removes. | GET tags, PATCH post |
| Excerpt | Required to publish, 80–200 chars, shown on cards and as the meta-description fallback. Live counter. | PATCH post |
| Meta title | Optional; falls back to `<title> · Udit N.`. Meter green at 50–60 chars, amber outside. | PATCH post |
| Meta description | Optional; falls back to the excerpt. Meter green at 140–160 chars. | PATCH post |
| Canonical URL | Defaults to `https://<site>/blog/<slug>` and is shown as a placeholder; only set it for cross-posts. Must be absolute https. | PATCH post |
| OpenGraph image | Optional, 1200×630 recommended; falls back to the cover. Same upload flow. | POST sign-upload, POST media, PATCH post |
| Search preview | Client only, built from the fields above and the site URL from the config endpoint. | GET editor-config |
| Before-publish checklist | Computed live in the browser from the same rule list the server enforces. Blockers: title, slug available, category, excerpt, 100+ words, every image has alt text. Warnings: cover, OG image, at least one tag, meta lengths. "Spelling pass" is dropped — nothing can verify it. | GET checklist (also returned by publish on failure) |

### Page chrome

| Control | How it should work | Endpoint |
| --- | --- | --- |
| Breadcrumbs, sidebar nav | Router links. Blogs is active. | client only |
| Who chip (U · Udit N. · Admin) | From the signed-in user. | GET /auth/me |
| Settings, Sign out | Settings is a placeholder route for now; Sign out calls logout and clears tokens. | POST /auth/logout |
| Leaving with unsaved changes | Flush autosave on route change; `beforeunload` warning if a save is still in flight. | PATCH post |

Two behaviours are worth calling out because they shape the data model:

- **When is a new post created?** Lazily. `/admin/blogs/new` holds the post in memory; the first autosave that has a title or body text calls POST create, then the URL becomes `/admin/blogs/:id/edit`. Clicking Add new post and leaving never leaves an empty draft behind.
- **Editing a live post must not change the live page.** Autosave only writes the working copy. The public page reads the published revision. **Update** snapshots the working copy and points the live page at it.

## Database schema changes

The spec's `blog_posts` row needs nine new columns and four new tables to support the editor. One Alembic migration covers all of it.

### `blog_posts` — the working copy

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk |  |
| title | text | 10–100 chars to publish |
| subtitle | text null | **new** |
| slug | citext | unique where `deleted_at is null` |
| slug\_locked | bool default false | **new** — true once edited by hand |
| content\_json | jsonb | **new** — TipTap doc, source of truth |
| content\_html | text | rendered by the server on every save |
| content\_text | text | **new** — plain text, for word count and search |
| search\_tsv | tsvector generated | **new** — from title, excerpt, content\_text; GIN index |
| content\_hash | char(64) | **new** — sha256 of the publishable fields; compared with the live revision's hash to compute `has_unpublished_changes` |
| excerpt | text null | 80–200 chars to publish |
| cover\_asset\_id | uuid fk media\_assets null | replaces `cover_image_url` |
| og\_asset\_id | uuid fk media\_assets null | **new** |
| category\_id | uuid fk blog\_categories null | replaces free-text `category` |
| tags | text\[\] default '{}' | GIN index |
| seo\_json | jsonb | `{meta_title, meta_description, canonical_url}`, all nullable |
| status | enum `draft, scheduled, published, archived` |  |
| visibility | enum `public, members, unlisted` | **new** |
| scheduled\_at | timestamptz null |  |
| published\_at | timestamptz null | set on first publish, never moved by Update |
| published\_revision\_id | uuid fk blog\_post\_revisions null | **new** — what the public page renders |
| word\_count, reading\_time\_min, block\_count | int | server-computed |
| is\_featured | bool default false | used by Blog Manager |
| version | int default 1 | optimistic lock, +1 on every write |
| author\_id | uuid fk users |  |
| created\_at, updated\_at, deleted\_at | timestamptz | soft delete |

### New tables

| Table | Key columns | Purpose |
| --- | --- | --- |
| blog\_post\_revisions | id, post\_id, kind (`publish` · `manual` · `restore`), snapshot jsonb, content\_hash, word\_count, created\_by, created\_at | Snapshot holds every publishable field. Publish revisions are kept forever; manual and restore revisions keep the latest 50 per post. |
| blog\_categories | id, slug, name, sort\_order, created\_at | Seeded with AI & Agents, Web Dev, Tutorials, Opinion, Career. |
| blog\_slug\_redirects | old\_slug pk, post\_id, created\_at | Written when a published post's slug changes; the public route answers 301. |
| admin\_activity\_log | id, actor\_id, action, entity\_type, entity\_id, summary, meta jsonb, created\_at | Written on publish, update, schedule, unschedule, unpublish, restore. Feeds the Dashboard "Recent activity" later. |

### `media_assets` additions

Add `width`, `height`, `bytes`, `format`, `alt_text`, `original_filename`, `purpose` (`cover` · `inline` · `og` · `other`) and `deleted_at`. Keep `public_id` unique.

The spec's `tags[]` array is kept instead of a join table: tag counts for the autocomplete and the Blog Manager tag cloud come from `unnest(tags)`, which is fast enough at portfolio scale.

## API endpoints — Blog Post Editor

The editor needs 22 endpoints under `/v1`; all except `/auth/*` require a Bearer JWT with `role=admin`. Writes that change a post carry the post's current `version` and get 409 if it moved.

### Endpoint list

| # | Short name | Method + path | Used by |
| --- | --- | --- | --- |
| 1 | editor-config | GET /admin/blog-editor/config | page load: limits, site URL, timezone, allowlists |
| 2 | create post | POST /admin/blogs | first autosave on `/new` |
| 3 | GET post | GET /admin/blogs/{id} | page load, preview |
| 4 | PATCH post | PATCH /admin/blogs/{id} | every autosave and rail field |
| 5 | slug-availability | GET /admin/blogs/slug-availability?slug=&exclude\_id= | slug line |
| 6 | checklist | GET /admin/blogs/{id}/checklist | checklist panel refresh |
| 7 | publish | POST /admin/blogs/{id}/publish | Publish / Update |
| 8 | schedule | POST /admin/blogs/{id}/schedule | Schedule / Reschedule |
| 9 | unschedule | DELETE /admin/blogs/{id}/schedule | Unschedule |
| 10 | unpublish | POST /admin/blogs/{id}/unpublish | ⋯ menu |
| 11 | discard-changes | POST /admin/blogs/{id}/discard-changes | ⋯ menu |
| 12 | create revision | POST /admin/blogs/{id}/revisions | Save draft, ⌘S |
| 13 | list revisions | GET /admin/blogs/{id}/revisions | revision drawer |
| 14 | get revision | GET /admin/blogs/{id}/revisions/{rev\_id} | revision preview |
| 15 | restore revision | POST /admin/blogs/{id}/revisions/{rev\_id}/restore | revision drawer |
| 16 | categories | GET /admin/blog-categories | category select |
| 17 | tags | GET /admin/blog-tags?q=&limit= | tag autocomplete |
| 18 | sign-upload | POST /admin/media/sign-upload | cover, inline image, OG |
| 19 | register media | POST /admin/media | after Cloudinary upload |
| 20 | list media | GET /admin/media?folder=&q=&cursor=&limit= | "browse library" modal |
| 21 | update media | PATCH /admin/media/{id} | edit alt text |
| 22 | embeds/resolve | POST /admin/embeds/resolve | video and embed buttons |

Existing spec endpoints reused as-is: `GET /auth/me`, `POST /auth/logout`, `POST /auth/refresh`. The spec's `POST /admin/media/upload` (multipart) is replaced by 18 + 19.

### Shared shapes

```json
// PostWritable — every field optional on PATCH; all nullable except tags
{
  "title": "Building Jerry: a study in style RAG",
  "subtitle": "How to make a frontier LLM sound like you...",
  "slug": "building-jerry-style-rag",
  "slug_locked": true,
  "content_json": { "type": "doc", "content": [ ... ] },
  "excerpt": "How to make a frontier LLM sound like you...",
  "cover_asset_id": "uuid",
  "og_asset_id": null,
  "category_id": "uuid",
  "tags": ["langgraph", "rag", "claude", "pgvector"],
  "visibility": "public",
  "seo": { "meta_title": null, "meta_description": "...", "canonical_url": null }
}

// PostDetail — returned by create, GET, publish, schedule, unpublish, discard, restore
{
  "id": "uuid",
  "version": 14,
  ...all PostWritable fields...,
  "content_html": "<p>...</p>",
  "cover": MediaAsset | null,
  "og_image": MediaAsset | null,
  "category": { "id": "uuid", "slug": "ai-agents", "name": "AI & Agents" } | null,
  "status": "draft" | "scheduled" | "published" | "archived",
  "scheduled_at": "2026-11-28T03:30:00Z" | null,
  "published_at": "2026-11-03T08:18:00Z" | null,
  "has_unpublished_changes": false,
  "public_url": "https://uditnarayana.dev/blog/building-jerry-style-rag" | null,
  "stats": { "word_count": 580, "reading_time_min": 3, "block_count": 12 },
  "seo_effective": { "meta_title": "... · Udit N.", "meta_description": "...", "canonical_url": "https://..." },
  "checklist": Checklist,
  "created_at": "...", "updated_at": "..."
}

// MediaAsset
{ "id": "uuid", "public_id": "blogs/9f2c/cover-a81", "url": "https://res.cloudinary.com/...",
  "width": 2400, "height": 1350, "format": "webp", "bytes": 412883,
  "alt_text": "Jerry architecture diagram", "purpose": "cover", "created_at": "..." }

// Checklist
{ "can_publish": false,
  "items": [ { "key": "excerpt", "label": "Excerpt written", "level": "blocker",
               "passed": false, "message": "Excerpt is 42 chars; needs 80-200." } ] }

// Error envelope — every 4xx/5xx
{ "error": { "code": "version_conflict", "message": "Post was changed in another tab.",
             "details": { "current_version": 15, "updated_at": "..." } } }
```

Checklist keys: `title`, `slug`, `category`, `excerpt`, `min_words`, `image_alt` (blockers) and `cover`, `og_image`, `tags`, `meta_title_length`, `meta_description_length` (warnings).

### Post lifecycle contracts

| # | Request | Success | Errors |
| --- | --- | --- | --- |
| 1 editor-config | — | 200 `{site_url, timezone: "Asia/Kolkata", title_suffix: " · Udit N.", limits: {title:[10,100], subtitle:160, excerpt:[80,200], meta_title:[50,60], meta_description:[140,160], tags_max:8, tag_len:[2,30], min_words:100, schedule_min_lead_minutes:5}, code_languages:[...], embed_providers:[...], upload: {max_bytes:10485760, formats:["jpg","png","webp"], min_cover_width:1200}}` | 401, 403 |
| 2 create post | PostWritable (title or body required) | 201 PostDetail; slug auto-made and de-duplicated | 422 `empty_post`, `invalid_content` |
| 3 GET post | — | 200 PostDetail | 404 |
| 4 PATCH post | `{version, ...PostWritable partial}` | 200 `{version, updated_at, slug, stats, content_hash, has_unpublished_changes, checklist}` — light, no HTML | 409 `version_conflict`, 409 `slug_taken`, 422 `invalid_content` (unknown node or mark, bad link scheme), 422 `validation_error`, 413 `content_too_large` (>1 MB JSON) |
| 5 slug-availability | query `slug`, `exclude_id` | 200 `{input, normalized, available, suggestion}` | 422 `reserved_slug` (new, preview, admin, tag, category, rss, feed) |
| 6 checklist | — | 200 Checklist | 404 |
| 7 publish | `{version}` | 200 PostDetail with `status: published`, `public_url`; writes a publish revision, sets `published_revision_id`; keeps `published_at` on Update; logs activity | 409 `version_conflict`, 422 `checklist_failed` + `details.checklist` |
| 8 schedule | `{version, scheduled_at}` (ISO with offset) | 200 PostDetail with `status: scheduled` | 409, 422 `checklist_failed`, 422 `schedule_in_past`, 409 `already_published` (use Update) |
| 9 unschedule | `{version}` | 200 PostDetail with `status: draft` | 409 `not_scheduled` |
| 10 unpublish | `{version}` | 200 PostDetail with `status: draft`, `published_revision_id: null`; public URL returns 404 | 409 `not_published` |
| 11 discard-changes | `{version}` | 200 PostDetail rebuilt from the live revision | 409 `not_published`, 409 `no_changes` |

### Revisions

| # | Request | Success | Errors |
| --- | --- | --- | --- |
| 12 create revision | `{version, label?}` (label ≤ 60 chars) | 201 RevisionSummary `{id, kind: "manual", label, word_count, created_at, is_live: false}`; no-op returns 200 with the latest revision if `content_hash` is unchanged | 409 |
| 13 list revisions | query `limit` (default 20), `cursor` | 200 `{items: RevisionSummary[], next_cursor}`, newest first, `is_live` marks the published one | 404 |
| 14 get revision | — | 200 `{...RevisionSummary, snapshot: PostWritable + content_html}` | 404 |
| 15 restore revision | `{version}` | 200 PostDetail; first saves the current working copy as a `restore` revision so nothing is lost; does not change the live page | 409 |

### Taxonomy

| # | Request | Success |
| --- | --- | --- |
| 16 categories | — | 200 `{items: [{id, slug, name, post_count}]}` ordered by `sort_order` |
| 17 tags | query `q` (prefix), `limit` (default 10) | 200 `{items: [{tag: "langgraph", count: 12}]}` most used first |

### Media and embeds

| # | Request | Success | Errors |
| --- | --- | --- | --- |
| 18 sign-upload | `{purpose: "cover" \| "inline" \| "og", post_id?, filename, bytes, mime}` | 200 `{upload_url, cloud_name, api_key, timestamp, signature, folder: "blogs/<post_id>", public_id, allowed_formats, max_bytes, expires_at}` — valid 10 min | 422 `file_too_large`, `unsupported_type` |
| 19 register media | `{public_id, version, signature, alt_text, purpose, original_filename}` — the values Cloudinary returned | 201 MediaAsset; server verifies Cloudinary's response signature (or looks the asset up via the Admin API) before inserting | 422 `invalid_upload_signature`, 422 `alt_required`, 422 `image_too_small` (cover < 1200 px) |
| 20 list media | query `folder` (default `blogs`), `q`, `cursor`, `limit` (default 24) | 200 `{items: MediaAsset[], next_cursor}` | — |
| 21 update media | `{alt_text}` | 200 MediaAsset; also rewrites `alt` on image nodes in posts that use it on their next save | 404 |
| 22 embeds/resolve | `{url, kind: "video" \| "embed"}` | 200 `{provider, original_url, embed_url, title, thumbnail_url, aspect_ratio: "16:9", height}` | 422 `unsupported_provider`, 422 `invalid_url` |

### TipTap node allowlist

The renderer accepts exactly these; anything else is a 422 `invalid_content`, which is what makes server-side HTML safe.

| Node or mark | Attributes |
| --- | --- |
| doc, paragraph, text, hardBreak, horizontalRule | — |
| heading | `level`: 2 or 3 (`id` slug generated by the renderer for the table of contents) |
| bulletList, orderedList (`start`), listItem, blockquote | — |
| codeBlock | `language` from the config list |
| table, tableRow, tableHeader, tableCell | `colspan`, `rowspan` |
| image | `asset_id` (required), `src`, `alt` (required), `caption`, `width`, `height` |
| callout | `variant`: info · tip · warning · danger; `title` |
| videoEmbed | `provider`, `embed_url`, `original_url`, `title` |
| embed | `provider`, `embed_url`, `height` (200–900) |
| marks: bold, italic, underline, strike, code | — |
| mark: link | `href` (https, http, mailto, or relative), `target` (`_blank` or null) |

## Cross-cutting rules

These rules apply to every editor endpoint; Claude Code should implement them once, as shared dependencies, not per route.

- **Auth.** A `require_admin` FastAPI dependency verifies the Supabase JWT (`SUPABASE_JWT_SECRET`) and the `role=admin` claim: 401 if missing or expired, 403 if not admin. A dev-only bypass (`ADMIN_DEV_BYPASS=true`) is allowed only when `ENV=development`.
- **Optimistic locking.** Every write takes `version`, updates `WHERE id = :id AND version = :version`, and bumps it. Zero rows updated means 409 `version_conflict` with the current version. The editor shows "Edited in another tab — reload / overwrite".
- **Autosave rhythm.** One request in flight at a time; edits made during a save are queued and merged into the next PATCH. Failed saves retry with backoff (2 s, 4 s, 8 s, then every 30 s) and the indicator shows "Offline, retrying".
- **Rendering.** The backend renders `content_html`, `content_text`, word count, reading time and heading ids from `content_json` on every create, PATCH and restore. All text is HTML-escaped; only allowlisted nodes, marks and URL schemes are emitted; iframes only for `embed_url`s produced by `embeds/resolve`.
- **Publishable hash.** `content_hash` = sha256 of the canonical JSON of title, subtitle, slug, content\_json, excerpt, cover, OG image, category, tags, visibility and SEO. `has_unpublished_changes` = post is published and its hash differs from the live revision's.
- **Time.** Store UTC `timestamptz`. The client sends ISO 8601 with offset and renders in `Asia/Kolkata` from editor-config.
- **Scheduling.** An APScheduler job runs every 60 s: `SELECT ... WHERE status = 'scheduled' AND scheduled_at <= now() FOR UPDATE SKIP LOCKED`, then runs the same publish service (checklist, revision, live pointer, activity log). If the checklist now fails, the post goes back to draft and an activity entry records why.
- **Public read path.** Public blog endpoints (built later) read only posts that are `published`, not deleted, and not `unlisted` in listings, rendering the snapshot behind `published_revision_id`. Old slugs resolve via `blog_slug_redirects` with a 301.
- **Rate limit.** 500 requests/min per admin token (spec §8). Autosave at one request per 1.5 s stays well inside it.
- **Activity log.** The publish service, scheduler, unschedule, unpublish, discard and restore each write one `admin_activity_log` row, e.g. `blog.published` · "Published 'Building Jerry'".

Post status transitions:

| From | Action | To |
| --- | --- | --- |
| (none) | first autosave | draft |
| draft | publish | published |
| draft | schedule | scheduled |
| scheduled | unschedule | draft |
| scheduled | scheduler fires | published |
| scheduled | reschedule | scheduled |
| published | edit (autosave) | published, with unpublished changes |
| published with changes | Update | published |
| published with changes | discard changes | published |
| published | unpublish | draft |
| any | archive (Blog Manager) | archived |

## Claude Code prompt — Blog Post Editor, end to end

Before pasting: export this doc as Markdown to `docs/specs/blog-editor-api.md`, and copy `New Blog Post.html` and `Blog Manager.html` to `docs/design/`. The prompt points Claude Code at both and asks it to plan before it codes.

```markdown
# Task: Build the Blog Post Editor end to end (admin only)

You are working in my portfolio monorepo: `portfolio/frontend` (React 18 + Vite, Zustand,
React Router) and `portfolio/backend` (FastAPI, Python 3.11, Postgres on Supabase).
Follow the folder layout in the spec §12 (`backend/app/api`, `models`, `services`, `db`,
`integrations`; `frontend/src/admin`, `components`, `hooks`, `stores`, `utils`).

## Read first
1. `docs/specs/blog-editor-api.md` — the API contract, schema, checklist rules and node
   allowlist. It is the source of truth; if code and spec disagree, ask me.
2. `docs/design/New Blog Post.html` — the approved editor design. Reproduce its layout,
   tokens (--paper, --ink, --accent ...), fonts (Caveat, Patrick Hand, JetBrains Mono,
   Source Serif 4) and components. Drop the Tweaks panel script.
3. `docs/design/Blog Manager.html` — only its sidebar and page header are needed now.

## Decisions already made (do not revisit)
- Content: TipTap JSON (`content_json`) is the source of truth. The client never sends
  HTML. The backend renders sanitized `content_html` from a fixed node allowlist.
- AI assist is OUT of this build: do not render the toolbar "AI assist" button, the
  floating ✨ button or the AI side panel. No /admin/ai endpoints.
- Images: signed direct upload to Cloudinary (backend signs, browser uploads, backend
  verifies and registers the asset). Do not proxy files through FastAPI.
- Revisions: snapshot on Publish/Update and on manual "Save draft"; autosave only
  overwrites the working copy. The public page renders `published_revision_id`.
- Design changes vs the mock: remove H1 from the toolbar (H2/H3 only); the rail's
  Draft/Scheduled/Publish control is read-only; cover drop zone and rail thumbnail edit
  the same field; drop the "Spelling pass" checklist item.

## Scope
### Backend
- One Alembic migration: everything in the spec's "Database schema changes" section,
  plus seed rows for blog_categories (AI & Agents, Web Dev, Tutorials, Opinion, Career).
- All 22 endpoints in the spec's endpoint list, with exactly the request/response shapes
  and error codes given there. Use Pydantic v2 models; one error envelope everywhere.
- Services, not fat routes: `blog_service` (create, patch, publish, schedule, unpublish,
  discard, restore), `render_service` (TipTap JSON -> HTML/text/stats/heading ids,
  rejects unknown nodes), `checklist_service` (one rule list, used by GET checklist,
  publish and the scheduler), `slug_service`, `media_service` (Cloudinary sign/verify via
  the `cloudinary` SDK), `embed_service` (provider allowlist + URL normalization).
- Shared dependencies: `require_admin` (Supabase JWT, role=admin; dev bypass only when
  ENV=development), optimistic locking on `version`, admin_activity_log writes.
- APScheduler job (every 60 s) that publishes due scheduled posts with
  `FOR UPDATE SKIP LOCKED`, reusing the publish service.
- Env vars: DATABASE_URL, SUPABASE_JWT_SECRET, CLOUDINARY_CLOUD_NAME,
  CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, SITE_URL, ADMIN_TIMEZONE=Asia/Kolkata.
  Add them to `.env.example`.

### Frontend
- Routes: `/admin/blogs` (Blog Manager placeholder), `/admin/blogs/new`,
  `/admin/blogs/:id/edit`, `/admin/blogs/:id/preview`. Protect `/admin/*` with an admin
  route guard.
- Blog Manager placeholder: render the sidebar + page header from Blog Manager.html and
  a single primary button "+ Add new post" linking to `/admin/blogs/new`. No table yet.
- Editor built with TipTap v2: StarterKit (heading levels 2-3), Underline, Link,
  Table kit, CodeBlockLowlight, Placeholder, CharacterCount, plus custom nodes
  `image` (asset_id/alt/caption), `callout` (variant/title), `videoEmbed`, `embed`.
  Slash menu with the same commands as the toolbar. Toolbar buttons show active state
  from the editor, not from click toggles.
- `useAutosave` hook: debounce 1.5 s, force-save every 30 s while typing, one request in
  flight, queue + merge edits, backoff retry, `beforeunload` guard, ⌘S/Ctrl+S = Save
  draft. Lazy create: `/new` creates the post on the first save that has a title or body
  text, then `history.replace` to `/:id/edit`.
- Zustand `editorStore`: post, version, save state, checklist, dirty fields.
- `api/blogEditor.ts`: typed client for every endpoint, attaching the JWT and handling
  401 -> refresh -> retry once.
- Publish bar states: Draft / Scheduled · date / Published / Published · unpublished
  changes. Publish becomes "Update" once live; a ⋯ menu has Discard changes and
  Unpublish. Schedule opens a date-time popover in IST. A failed checklist opens the
  checklist panel with blockers highlighted.
- Conflict banner on 409 version_conflict: "Edited in another tab" with Reload.
- Revision drawer (from a "History" link in the publish bar): list, preview, restore.
- Media picker modal: upload tab (drag-drop, alt text required) and library tab
  (GET /admin/media, infinite scroll). Used for cover, inline images and OG image.
- Rail: tags chips with autocomplete, category select, visibility, excerpt + SEO fields
  with the character meters and limits from GET /admin/blog-editor/config, live search
  preview, live checklist computed client-side from the same rules.
- Preview page renders `content_html` inside a public-post template with highlighted code.

### Tests
- Backend (pytest + httpx AsyncClient, test DB): render_service for every allowlisted
  node and rejection of unknown nodes / javascript: links; PATCH version conflict;
  publish blocked by checklist; publish -> edit -> has_unpublished_changes -> Update and
  Discard; slug clash suggestion and published-slug redirect; scheduler publishes a due
  post; sign-upload and register-media with a mocked Cloudinary.
- Frontend (Vitest + React Testing Library): useAutosave debounce/queue/retry; checklist
  rules; tag normalization.

## Out of scope (do not build)
Blog Manager table, filters, bulk actions, comment moderation; Dashboard Overview;
public blog pages beyond the admin preview; AI assist; newsletter.

## How to work
1. First read the spec and designs, then reply with a plan: files you will create or
   change, the migration, and any spec gaps or contradictions you found. Wait for my
   approval before writing code.
2. Build in this order, committing after each: migration -> render + checklist services
   with tests -> remaining backend endpoints with tests -> frontend API client + store ->
   editor UI -> media picker -> publish/schedule/revisions UI -> Blog Manager placeholder.
3. Never invent endpoint shapes; if something is missing from the spec, ask.
4. Done means: `pytest` and `vitest` pass, `ruff` and `eslint` are clean, and I can
   click "+ Add new post", write a post with an image, a code block, a callout and a
   table, autosave, preview it, schedule it, publish it, edit it, and Update it.
```

## Look-ahead — Blog Manager and Dashboard Overview

These are the next two builds; full request/response contracts get written when we reach each one. Listed now so the editor's schema already supports them.

### Blog Manager (next)

| Method + path | Purpose |
| --- | --- |
| GET /admin/blogs?status=&category=&tag=&q=&sort=&page=&limit= | Table rows: cover, title, excerpt, slug, status, category, tags, reading time, views / reactions / comments / pending comments, author, date |
| GET /admin/blogs/stats | Stats strip: total, published, drafts, scheduled (+ next run), pending comments, posts this month |
| GET /admin/blog-tags?limit=50 | Tag cloud (same endpoint as the editor, larger limit) |
| POST /admin/blogs/bulk | `{ids, action: publish \| schedule \| feature \| unfeature \| archive \| delete, scheduled_at?}` → per-id results |
| PATCH /admin/blogs/{id}/feature | Star toggle on the cover |
| POST /admin/blogs/{id}/archive · DELETE /admin/blogs/{id} | Row actions (soft delete) |
| GET /admin/comments?status=pending&blog\_id= | Moderation queue and banner count |
| POST /admin/comments/{id}/approve · DELETE /admin/comments/{id} · POST /admin/comments/bulk | Moderation actions |
| POST/PATCH/DELETE /admin/blog-categories | Manage the category list |

Open question: the mock's **Import** button — import from where (Markdown files, Medium, dev.to)? Until decided, I'd leave it out.

### Dashboard Overview — Overview page

| Method + path | Purpose |
| --- | --- |
| GET /admin/analytics/overview | Hero + mini stats (spec §8.7, extended with comments queue and unread notes) |
| GET /admin/activity?limit=10 | Activity stream, read from `admin_activity_log` |
| GET /admin/health | API, Supabase, Cloudinary usage, LLM, Google Calendar |
| GET /admin/analytics/top-content?range=today&limit=1 | "Top page · today" card |

Quick-create buttons are plain links (New post → `/admin/blogs/new`).

### Dashboard Overview — new "Homepage" page

Every homepage field is optional: the public `GET /home` omits empty fields and the site skips rendering them. "See my work" and "Reach out" stay hard-coded to `#projects` and `#contact`; Education and Contact stay hard-coded; Projects and Live sites come from Project Manager; Blogs from Blog Manager.

| Method + path | Edits |
| --- | --- |
| GET /admin/home | Everything below, for the admin page |
| PUT /admin/home/hero | Availability pill, headline (one `*accent*` word), subline, typewriter role pairs, portrait asset, Focus card, Now-at card, Currently-building card (+ link), marquee items |
| PUT /admin/home/about | Hello paragraph, signature, social links (GitHub, LinkedIn, email, X, blog — empty ones hide their icon) |
| PUT /admin/home/what-i-do | Title, subline, tech chips, 3–4 points (only if you want this section editable too) |
| GET / POST / PATCH / DELETE /admin/home/skill-categories\[/{id}\] + PATCH …/reorder | Proficiency tabs |
| GET / POST / PATCH / DELETE /admin/home/skill-categories/{id}/skills\[/{skill\_id}\] + reorder | Skills with level 1–5 |
| GET / POST / PATCH / DELETE /admin/home/experiences\[/{id}\] + PATCH /admin/home/experiences/reorder | Company, logo initials or logo asset, brand colour, role, start, end (null = Present), description, exactly 2 bullets |
| GET /home (public) | One aggregate read for the portfolio page |

Two layout cases to settle before building the Homepage page:

- The hero bento grid assumes all four cards. If the portrait is empty the remaining cards need a fallback grid, otherwise the column looks broken.
- The portfolio shows level labels only for 3, 4 and 5 (Working, Advanced, Expert). Levels 1–2 need labels, e.g. Learning and Familiar, or the admin should only offer 3–5.

## Content limits for homepage fields

Experience descriptions should be **60–80 characters (about 10–14 words), hard cap 90**, and each bullet **up to 55 characters (about 8–9 words), hard cap 65**. These keep every card at the same height and inside 3 lines of description and 2 lines per bullet.

How I got there: the four experience cards share the 1,200 px content width, so each is about 263 px wide with roughly 223 px for text. At the card's font sizes that fits about 33 characters per line of description (13.5 px) and about 33 per bullet line (13 px, indented). Your 70-character target lands at two lines — a good fit.

The admin form should show a live counter, turn amber at the target and refuse input past the hard cap.

| Section | Field | Target | Hard cap | Why |
| --- | --- | --- | --- | --- |
| Experience | Company (banner) | ≤ 16 chars | 18 | one line, 20 px bold, centred |
| Experience | Logo initials | 1–3 chars | 3 | 62 px circle |
| Experience | Role | ≤ 26 chars | 40 | one line ideal, two at most |
| Experience | Dates | month + year → shown as "2025 — Present" | — | end empty = Present |
| Experience | Description | 60–80 chars | 90 | 2–3 lines |
| Experience | Bullets | exactly 2, ≤ 55 chars each | 65 | 2 lines each |
| Hero | Availability pill | ≤ 36 chars | 40 | one-line pill |
| Hero | Headline | ≤ 36 chars, 3 lines | 40 | up to 88 px type |
| Hero | Subline | ≤ 140 chars | 160 | 44-character measure, 3–4 lines |
| Hero | Typewriter pairs | 2–5 pairs; role ≤ 24, tag ≤ 18 | 28 / 20 | one line under the headline |
| Hero | Focus card big / small | ≤ 12 / ≤ 36 chars | 14 / 40 | half-width card, 34 px big text |
| Hero | Now-at big / small | ≤ 10 / ≤ 36 chars | 12 / 40 | same card size |
| Hero | Currently building | ≤ 36 chars | 44 | one line in the wide card |
| Hero | Marquee items | 6–14 items, ≤ 16 chars each | 18 | scrolling strip |
| Hello | Paragraph | ≤ 280 chars (about 45 words) | 320 | large 21–30 px type, 820 px column |
| Hello | Signature | ≤ 24 chars | 30 |  |
| Proficiency | Category tab label | ≤ 22 chars | 26 | tab pill |
| Proficiency | Skills per category | 3–6 | 6 | the constellation gets crowded past 6 nodes |
| Proficiency | Skill name | ≤ 24 chars | 28 | the canvas shows only the part before " / " or " + " |
| What I do | Points | 3–4, ≤ 100 chars each | 120 | two lines each |

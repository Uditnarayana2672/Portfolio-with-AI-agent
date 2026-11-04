# Blog Manager — Build Plan

Nov 4, 2026 · Udit N. · Companion to **Blog Manager API.md** (endpoints 24–27)

---

## 1. Scope

**In**
- The admin Blog Manager page at `/admin/blogs`, replacing today's placeholder (`Portfolio_UI/src/pages/BlogManagerPage.tsx`): stats cards, status and category pills, search, table, row click → editor, bulk Archive / Delete, pagination.
- Backend endpoints 24–27 and one additive migration (`006_blog_manager`).
- Three fixes to the blog editor already built: the cover image is cropped, inline images and videos are too large (and images need zoom), and a 500 error.

**Out (later)**
- Pending comments card, moderation banner and comment counts. They come with the public blog page.
- Tag cloud (removed from the design).
- Publish, Schedule and Feature from the manager. These are editor-only by design.
- ✨ AI assist and ↗ Open (public page). The buttons are hidden until those features exist.
- Semantic search (§11).

---

## 2. What already exists

### 2.1 Schema (live Supabase, after `005_blog_editor_schema`)

| Table | Columns the manager uses | Notes |
| --- | --- | --- |
| `blog_posts` | `id, title, slug, excerpt, status, category_id, tags, cover_asset_id, read_time, word_count, views, author_id, version, published_revision_id, content_hash, content_text, scheduled_at, schedule_error, published_at, last_published_at, created_at, updated_at` | Indexes: `status`, `category_id`, `tags` (GIN), `published_at`, FTS GIN `idx_blog_posts_search` (title + subtitle + excerpt + content_text, unweighted), trigram `idx_blog_posts_title_trgm`, `idx_blog_posts_due`. Check constraints: scheduled ⇔ `scheduled_at`, published ⇒ revision, slug format. |
| `blog_post_revisions` | `id, content_hash` | Needed for `has_unpublished_changes` (join on `published_revision_id`). |
| `blog_categories` | `id, name, slug, sort_order` | 5 seeded categories. `GET /admin/blog-categories` already returns `post_count`. |
| `media_assets` | `id, cloudinary_url, public_id, alt_text` | Cover thumbnails (join on `cover_asset_id`). |
| `users` | `id, name` | Author column. |
| `comments` | `blog_id → blog_posts.id` | **No `ON DELETE` rule.** Deleting a post that has comments fails with a foreign key error (500). It's harmless today (no comments yet) but must be fixed before delete ships (§3). |
| `reactions` | `content_type, content_id` | Polymorphic, no FK. Rows must be cleaned up in code on delete. |
| `activity_log` | enum already has `blog_archived`, `blog_deleted`, `blog_updated`, `blog_unscheduled` | No enum migration needed. |
| enum `blog_status` | `draft, review, published, archived, scheduled` | `archived` exists but **nothing can set it yet**: there's no archive endpoint. `review` is unused and stays hidden. |

### 2.2 What's missing for this page

| Need | Gap |
| --- | --- |
| A list of posts | There is **no** `GET /admin/blogs` list endpoint. The blog router only has editor endpoints. |
| Counts for cards and pills | None. |
| Archive / restore | No endpoint and no `archived_at` column. Archived posts would be stuck forever, because the editor is read-only for them (`POST_ARCHIVED`). |
| Bulk delete | The single `DELETE` only allows never-published drafts. |
| Ranked search | The FTS index is unweighted, so title hits can't be ranked above body hits. |

### 2.3 Reused as-is

- `GET /admin/blogs/{id}` (endpoint 3): row click → editor. **Already works**, because `/admin/blogs/:id/edit` loads the post through the existing editor code. Nothing new is needed for "open prefilled, ready to edit".
- `GET /admin/blog-categories`: pill labels and order.
- `get_current_admin`, the `domain_errors()` mapper, `BlogPostWorkflow.record()` (activity log), `BlogPostWorkflow.load()` (ownership + 404), `_like_escape`.
- `POST /admin/projects/bulk` as the pattern (ownership check, action dispatch). It isn't called; see API §2.
- Frontend: `Sidebar`, `Pagination`, `EmptyState`, `DeleteModal`, `SearchInput`, the `MiniStat` styling, the page header CSS in `BlogEditorPage.module.css`, and `request()` in `api/blogApi.ts`.

---

## 3. Database migration — `006_blog_manager` (additive only)

Apply in Supabase as `blog_manager` (migrations are tracked in Supabase; mirror in `alembic/versions/006_blog_manager.py` and `supabase/migrations/006_blog_manager.sql`, same as 005).

```sql
-- 1. Archive timestamp (shown as "archived 3d ago", sortable).
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
```

Why this doesn't disturb existing APIs:
- New columns are nullable or generated. No existing insert or update has to change. The ORM maps `search_vector` as `Computed(..., persisted=True)` + `deferred()`, so it's never written and never loaded by `get()`.
- The `archived_at` check holds today: no row is archived yet, and the backfill covers any that are.
- `idx_blog_posts_search` (old, unweighted) stays. Nothing depends on it except possible future use. Drop it in a later cleanup once the new index is confirmed in `EXPLAIN`.
- Changing the `comments` FK only changes delete behaviour, and nothing deletes posts with comments today.
- Tags aren't in the vector (`array_to_string` isn't immutable, so it can't be used in a generated column). They're matched with `tags && :words` on the existing GIN index.

Rollback: drop the two indexes and the two columns, and restore the FK without the cascade.

---

## 4. Backend build (FastAPI, same onion layers as the editor)

### 4.1 Files

| File | Change |
| --- | --- |
| `app/application/use_cases/blog/manager.py` | **new**: `ListBlogPosts`, `GetBlogStats`, `BulkBlogAction`, `UnarchiveBlogPost` |
| `app/application/dtos/blog.py` | add `PostListFilters`, `PostListItemView`, `PostListResult`, `BlogStatsView`, `BulkResultView`, `LIST_STATUSES`, `LIST_SORTS` |
| `app/domain/repositories/blog_post_repository.py` | add abstract `list_posts`, `facet_counts`, `status_stats`, `lock_many` |
| `app/infrastructure/persistence/repositories/blog_post_repository.py` | implement them (§4.3); `delete()` also removes `reactions` rows |
| `app/domain/entities/blog_post.py` | add `archived_at` to `BlogPost`; new `PostListRow` |
| `app/infrastructure/persistence/orm/models.py` | `archived_at`, deferred `search_vector` |
| `app/application/use_cases/blog/post_workflow.py` | `archive(post, actor)` helper used by bulk (clears schedule, sets `archived_at`, logs) |
| `app/api/v1/schemas/blog.py` | `PostListItemResponse`, `PostListResponse`, `BlogStatsResponse`, `BulkRequest`, `BulkResultResponse` |
| `app/api/v1/endpoints/blogs.py` | 4 routes; `stats` and `bulk` registered **above** `/{post_id}` |
| `app/api/v1/dependencies/providers.py` | 4 providers |
| `tests/test_blog_manager.py` | **new** (§10) |

### 4.2 Use case rules

- **ListBlogPosts**: validates params (API §4.1), normalizes `status` (repeatable or comma list, deduplicated), and treats `q` shorter than 2 characters or punctuation only as no search. Then it runs `list_posts` and `facet_counts` and maps rows to views. `excerpt` falls back to the first 160 characters of `content_text`. `has_unpublished_changes` comes from the joined live hash.
- **BulkBlogAction**: for each item it opens a `begin_nested()` savepoint, locks the row, checks the version and ownership, applies the rule table (API §4.3), and records success or failure. A failure rolls back only its own savepoint. All rows are locked **in id order** so two overlapping bulk calls can't deadlock.
- **UnarchiveBlogPost**: `archived` → `draft`, clears `archived_at`, returns `wf.view(post)`.
- **Archive** reuses the lock, version check and activity logging the publish use cases already use. When it archives a `published` post it doesn't create a revision; the live revision stays for history and media usage.

### 4.3 The list query (one round trip for rows + total)

```sql
with base as (
  select p.id, p.title, p.slug, p.excerpt, left(p.content_text, 160) as body_start,
         p.status, p.category_id, p.tags, p.read_time, p.word_count, p.views, p.version,
         p.scheduled_at, p.schedule_error, p.published_at, p.archived_at,
         p.created_at, p.updated_at, p.author_id, p.cover_asset_id,
         (p.content_hash is distinct from r.content_hash) as changed_since_live,
         -- only when q is set:
         websearch_to_tsquery('english', :q) as tq
  from blog_posts p
  left join blog_post_revisions r on r.id = p.published_revision_id
  where (:statuses is null and p.status <> 'archived' or p.status = any(:statuses))
    and (:category is null or p.category_id = :category or (:category = 'none' and p.category_id is null))
    and (:q is null or p.search_vector @@ (websearch_to_tsquery('english', :q) || to_tsquery('english', :last_word_prefix))
                    or p.title ilike :like or p.slug ilike :slug_like
                    or p.tags && :words or word_similarity(:q, p.title) > 0.4)
)
select base.*, count(*) over () as total, <rank expr> as rank
from base
order by <sort>, id
limit :limit offset :offset;
```

Then one small query joins `blog_categories`, `media_assets` (cover thumbnail) and `users` for the ids on the page. Build the query with SQLAlchemy Core, not string formatting. Build the prefix tsquery from sanitized words (`[a-z0-9]+` only) so `to_tsquery` can never get syntax errors from user input.

**Facets**: one query with two `GROUP BY` blocks over the same `WHERE`, each leaving out its own dimension:

```sql
select 'status' as dim, status::text as key, count(*) from blog_posts where <category AND search> group by status
union all
select 'category', coalesce(category_id::text, 'none'), count(*) from blog_posts where <status AND search> group by category_id;
```

`all` for status = sum of the non-archived keys. With fewer than 1,000 posts these are sub-millisecond, so no caching.

### 4.4 Checks for each endpoint

- `GET /admin/blogs` with no params returns the same set as the default view of the design (non-archived, newest edit first).
- `status=archived` returns only archived posts. `status=draft&status=archived` returns both.
- A search for a title word ranks that post above a post that has the word only in its body.

---

## 5. Frontend build (`Portfolio_UI`)

### 5.1 Files

| File | Purpose |
| --- | --- |
| `src/pages/BlogManagerPage.tsx` (+ `.module.css`) | Replace the placeholder. Layout per `Blog Manager.html` minus the removed parts. |
| `src/api/blogApi.ts` | `listPosts(params, signal)`, `getBlogStats()`, `bulkPosts(action, items)`, `unarchivePost(id, version)` |
| `src/types/blog.ts` | `PostListItem`, `PostListResponse`, `BlogStats`, `BulkResult` |
| `src/hooks/useBlogListParams.ts` | Reads and writes `status[]`, `category`, `q`, `sort`, `dir`, `page` in the URL (`useSearchParams`). Changing any filter resets `page`. |
| `src/hooks/useBlogList.ts` | Fetches with `AbortController`, debounces `q` by 250 ms, keeps the previous rows visible while loading (no flicker), refetches on window focus. |
| `src/components/blogManager/StatsCards.tsx` | Four `MiniStat` cards from `/stats` |
| `src/components/blogManager/FilterPills.tsx` | Status (multi) + category (single) + sort pill; counts from `facets` |
| `src/components/blogManager/PostsTable.tsx`, `PostRow.tsx` | Table; row is a link to `/admin/blogs/{id}/edit` |
| `src/components/blogManager/BlogBulkBar.tsx` | "N selected · ▭ Archive · ✕ Delete · Clear" |
| `src/components/blogManager/ConfirmBulkModal.tsx` | Lists titles; warns which can't be deleted; type-to-confirm (API M5) |
| `src/store/blogManagerStore.ts` | Selection only: `Map<id, version>` so bulk calls can send versions, kept across pages |

### 5.2 Pill behaviour (the core requirement)

```ts
// status: string[]  ([] = All)
toggleStatus(s) → next = cur.includes(s) ? cur.filter(x => x !== s) : [...cur, s]
clickAll()      → []
// All pill: active when status.length === 0; otherwise greyed (still clickable to reset)
// category: string | null (null = All); clicking a category replaces it
```

The request sends `status` repeated and `category_id`. Counts on each pill come from `facets`, so "AI & Agents 14" updates to "AI & Agents 3" when **Draft** is selected.

### 5.3 Row click → editor

- The title cell and the row body are wrapped in `<Link to={`/admin/blogs/${id}/edit`}>` (a stretched link), so ⌘-click opens a new tab and the rows work with a keyboard.
- The checkbox and action buttons call `e.stopPropagation()` and sit above the stretched link (`position: relative; z-index: 1`).
- The editor already loads the post into the "New post" layout with every field prefilled (`GET /admin/blogs/{id}`). No editor change is needed, except the archived banner, which gets a **Restore to drafts** button (endpoint 27).
- Before navigating, save `window.scrollY` in `sessionStorage` under the list URL, and restore it on return (API M14).

### 5.4 Bulk bar

- Hidden when nothing is selected. Shows **only Archive and Delete**.
- Delete opens `ConfirmBulkModal`. It splits the selection into "will be deleted" and "can't be deleted — archive instead" using the row statuses, and offers **Archive those instead**.
- After the call: toast "2 archived · 1 skipped (changed in another tab)", refetch the list and stats, and keep only the failed ids selected.

### 5.5 Status and row details

| Row state | Status chip | Date column |
| --- | --- | --- |
| published | ● Published (green); "· edited" if `has_unpublished_changes` | `published_at` |
| scheduled | ● Scheduled · Tue 09:00 IST (blue) | `scheduled_at` |
| draft | ○ Draft · 1,240 words (dashed); ⚠ "Schedule failed" if `schedule_error` | "edited 2h ago" |
| archived | ▭ Archived (grey) + ↺ Restore action | "archived 3d ago" |

Empty states: no posts at all ("Write your first post" → New post), no search results (API M9), page past the end (go to the last page).

---

## 6. Search architecture (decision)

The full decision is in **API §5**. In short: **keyword full-text + fuzzy title matching in Postgres**, ranked title > tag/slug > subtitle/excerpt > body, with prefix matching while typing and `<mark>` snippets. It's fast enough for type-ahead, finds exact matches first, and uses indexes that already exist plus one new generated column. Semantic (vector) search is a later phase for the public blog (§11).

---

## 7. Fix 1 — the cover image is cropped

**Cause (two places):**
1. **Editor**: `BlogEditorPage.tsx:151` asks Cloudinary for `w_1400,h_520,c_fill`. `c_fill` crops the image to a 2.7:1 strip on the server, so a portrait or 16:9 cover loses most of its height as soon as it's uploaded.
2. **Reader / preview**: `styles/blogArticle.css:15`, `.bp-cover img { max-height: 460px; object-fit: cover; }`, crops whatever is left with CSS.

**Fix: show the whole image, centred.**
- Editor: use `f_auto,q_auto,w_1400,c_limit` (resize only, never crop).
- Reader CSS:
  ```css
  .bp-cover { margin: 0 -28px 28px; display: flex; justify-content: center;
              background: var(--paper-dark); border-block: 1.5px solid var(--ink); }
  .bp-cover img { display: block; width: auto; max-width: 100%; height: auto;
                  max-height: min(70vh, 640px); object-fit: contain; margin: 0 auto; }
  ```
  The whole image is always visible and centred. A tall image gets paper-coloured side bands instead of being cut off.
- Server: the cover payload already sends `width` and `height`. Output them as `width`/`height` attributes on the `<img>` so the browser reserves the right space (no layout jump).
- Keep `c_fill` only where a crop is the point: the rail **Card preview**, the social card (1200×630) and the Blog Manager table thumbnail. Those are labelled previews of cards, not the article.
- Check: upload a portrait (3:4), a square, and a 21:9 image. Each must be fully visible and centred in the editor, the preview and the revision viewer.

---

## 8. Fix 2 — inline images and videos are too large; zoom for images

**Cause:** the image node only has `size = normal | wide | full`, and `normal` is 100 % of the 760 px column (`.bp-image img { width: 100% }`). A small screenshot gets stretched to the full width. Videos are always `width: 100%` at 16:9.

### 8.1 Sizes (content schema change, backward compatible)

| `size` | Max width | Default for |
| --- | --- | --- |
| `small` | 360 px | — |
| `medium` | 560 px | **new images and videos** |
| `normal` (label "Large") | 760 px (column) | existing posts. Unchanged, so nothing already written moves. |
| `wide` | 880 px | |
| `full` | full bleed | |

- `content_schema.py`: `image.size` enum gains `small`, `medium`; `video` gains `size` (`small | medium | normal`, default `medium`). Unknown values still fall back to the default. No DB migration (JSON content), and `content_schema_version` doesn't need to change because the change is purely additive.
- **Never upscale:** the renderer sets `max-width: min(<size>, <natural width>px)` inline from the stored `width`, so a 300 px screenshot is never blown up to 560 px.
- Images and videos are centred (`margin-inline: auto`), and the caption follows the media width.
- Editor: the node view's size `<select>` gets the new options, the editor CSS mirrors the same max-widths so the editor matches the page, and inserts default to `medium` (`editorBridge.imageAttrs`).
- The renderer's `sizes` attribute follows the size (`(max-width: 600px) 100vw, 560px` for medium), so the browser downloads a smaller file too.

### 8.2 Zoom in / out inside the image frame (reader page)

Added to `src/lib/blogArticleBehaviour.ts` (already used by the preview and meant for the public page), progressive enhancement:

- Every `.bp-image` figure gets a frame (`overflow: hidden`) and a small control group: **−**, **+**, **⟲ reset**, plus a % readout. The controls appear on hover or focus and are always visible on touch screens.
- Zoom 1×–4× in 0.5 steps. **Ctrl/⌘ + wheel** or **pinch** zooms around the cursor or fingers. A plain wheel still scrolls the page (no scroll-jacking). **Double-click / double-tap** toggles between 1× and 2×.
- While zoomed: drag (or one-finger pan) moves the image, clamped so it can't be dragged out of the frame. Esc or reset goes back to 1×.
- Sharpness: on the first zoom, swap in a high-resolution source (`data-zoom-src`, Cloudinary `w_2000,c_limit`) emitted by the renderer.
- The frame keeps its size; only the image transforms (`transform: translate() scale()`, `will-change` only while zooming).
- Accessibility: the buttons are real `<button>`s with labels, `+`/`-`/`0` keys work when the figure has focus, and `prefers-reduced-motion` disables the transition.
- The editor gets no zoom (it conflicts with selecting text and dragging blocks).

---

## 9. Fix 3 — the 500 error

**Status: not reproduced yet.**

What I checked:
- `tests/test_blog_editor.py`: **33 passed**. The tests use in-memory fakes, so they can't catch errors that only the real database produces (constraint violations, enum values, triggers).
- Every route the frontend calls (`src/api/blogApi.ts`) exists in `blogs.py` / `blog_taxonomy.py` with matching methods. A mismatch would give a 404 or 405, not a 500.
- The uvicorn server on port 8000 writes to its terminal, not to a file. `server.log` and `server_err.log` in the repo are old and contain no 500.
- I tried to replay every blog endpoint against the live database inside a transaction that's always rolled back. The permission check blocked it because it touches shared data, so the live-DB run is still to do.

**Places in the code where a 500 can happen:**

| # | Where | Trigger | Fix |
| --- | --- | --- | --- |
| a | Any write | A DB constraint (`IntegrityError`) is not mapped by `domain_errors()`. For example, two autosaves race to the same slug, or a value breaks `blog_posts_slug_format`. | Map `IntegrityError` → 409 `CONFLICT` with the constraint name, then retry slug generation once on `blog_posts_slug_key`. |
| b | `DELETE` (endpoint 5, and bulk later) | The `comments.blog_id` FK has no cascade. | Migration §3.4. |
| c | `post_workflow._json_default` | Raises `TypeError` for anything other than UUID or datetime (for example a `date` or `Decimal` in `seo` or the snapshot). | Fall back to `str()` instead of raising. |
| d | Every endpoint | Unhandled exceptions return a plain-text 500 and the traceback is lost when the terminal scrolls. | Add an app-wide exception handler in `main.py`: log the traceback with a request id and return the standard envelope `{"error":"INTERNAL","message":…,"detail":{"request_id":…}}`. Add a file log handler (`logs/api.log`, rotating). |

**To pin it down:** reproduce it once in the UI and copy the traceback from the uvicorn terminal (or the failing request from DevTools → Network: method, URL and response). With that it's a targeted fix. Step (d) is worth doing regardless, so the next one is logged with a request id.

---

## 10. Tests

**Backend (`tests/test_blog_manager.py`, plus a live-DB smoke run in a rolled-back transaction):**
- Filters: All excludes archived; each status alone; multiple statuses; status × category; `category_id=none`; an unknown category gives 0 items; invalid params give 422.
- Facets cross-filter correctly (status counts ignore the status filter, and so on).
- Search: a title hit ranks above a body hit; the prefix `graph mem` finds "memory"; the typo `memry` finds "memory"; a tag match works; punctuation-only queries are ignored; `%` and `_` are taken literally.
- Pagination is stable with equal `updated_at` values; a page past the end returns empty with the right `total_pages`.
- Bulk archive for each status; scheduled → `scheduled_at` cleared; already archived → per-item failure; version conflict → per-item failure while others succeed; ownership.
- Bulk delete: never-published draft ok; archived ok; published, unpublished-draft and scheduled are refused; a post with comments is deleted (cascade).
- Unarchive → draft and keeps `published_at`; unarchive of a non-archived post → 409.
- The `archived_at` check constraint holds after every transition.

**Frontend:**
- Pill logic unit test (§5.2).
- Playwright: filter combinations update rows and counts; row click opens a prefilled editor; checkbox doesn't navigate; the bulk bar shows only Archive and Delete; mixed delete warning; back keeps filters and scroll.
- Visual checks for the cover (portrait, square, panorama) and the image sizes and zoom (mouse, trackpad pinch, touch, keyboard).

---

## 11. Build order and done criteria

| Step | Work | Done when |
| --- | --- | --- |
| 0 | **500 fix:** get the traceback, fix it, add the global handler and the file log (§9 d) | The failing action works and errors are logged with a request id |
| 1 | Migration `006_blog_manager` (Supabase + alembic + ORM) | `EXPLAIN` uses `idx_blog_posts_search_vector`; existing editor tests pass |
| 2 | Repo + use cases + endpoints 24–27 + tests | `pytest` green; live smoke run (rolled back) gives no 500 |
| 3 | Frontend list: cards, pills, search, table, pagination, URL state | Filter combinations match the API §6 table |
| 4 | Row → editor; bulk Archive/Delete + confirm; Restore | Playwright flows pass |
| 5 | Cover fix (§7) | Three aspect ratios fully visible and centred |
| 6 | Media sizes + zoom (§8) | New images default to medium; old posts unchanged; zoom works on mouse, touch and keyboard |
| 7 | Docs: update New Blog Post API §7 / §8 with archive; add implementation notes here | — |

Steps 5–6 don't depend on 1–4 and can go first if you want the editor fixes before the manager.

**Later phase: semantic search.** Add `blog_posts.embedding vector(1024)`, embedded on publish (not on every autosave) from title + excerpt + headings. Use it for the public search and "related posts". Combine it with the keyword rank (reciprocal rank fusion) behind a `mode=semantic` flag on the public endpoint. The admin list keeps keyword search.

---

## 12. Open questions

1. **"All" excludes archived.** That's the plan. Say if you'd rather have All include archived posts.
2. **Bulk delete of archived posts that were once published** is allowed in the plan, which permanently removes a page that used to be public. The alternative is "archived stays forever, delete only never-published drafts".
3. **Category pills are single-select.** Should categories be multi-select like statuses?
4. **Default size for new images:** medium (560 px) is proposed. Should screenshots default to "small"?
5. **The 500:** which action triggers it? (Paste the traceback or the failing request.)

---

## 13. Implementation notes (as built, Nov 4, 2026)

Where the code differs from the sections above:

| Topic | As built |
| --- | --- |
| List queries | A separate read-side port, `BlogListRepository` (`app/domain/repositories/blog_list_repository.py`, SQL in `…/repositories/blog_list_repository.py`), instead of new abstract methods on `BlogPostRepository`. This keeps the editor's contract (and its test fakes) unchanged. Archive, delete and restore go through `BlogPostWorkflow` and the existing repository. |
| Bulk savepoints | Not used. Every rule for a post is checked before anything is written for it, so a refused post leaves no partial change. Rows are locked in id order. An unexpected DB error still fails the whole request (rolled back). |
| Delete | `SqlAlchemyBlogPostRepository.delete()` also removes the post's `reactions` and `comments` explicitly, so it works before and after migration 006. |
| Media sizes | Schema default stays `normal` (existing posts unchanged); the editor inserts `medium`. The renderer wraps images in `.bp-image__frame`, sets an inline `max-width` (size cap, never above the file's width), a per-size `sizes` hint and `data-zoom-src`. Videos get `size` too (`small \| medium \| normal`). |
| Zoom | `setupImageZoom` in `src/lib/blogArticleBehaviour.ts`, wired by `enhanceArticle`. Images inside a link are skipped (the link keeps its click). |
| 500 hardening | `domain_errors()` maps `IntegrityError` → 409 `CONFLICT` with the constraint name. `_json_default` stringifies unknown types instead of raising. The global handler returns a `request_id` (also in `X-Request-Id`) and errors are logged to `logs/api.log` (rotating, git-ignored). The original 500 is still unidentified (§9). |
| Frontend structure | One page file (`BlogManagerPage.tsx`, same pattern as `ProjectManagerPage.tsx`) plus `src/lib/blogManagerFilters.ts` for URL state and pill logic, instead of the component split in §5.1. |
| Archived posts in the editor | Banner with **↺ Restore to drafts**; the editor area is `inert` (read-only) while archived. |

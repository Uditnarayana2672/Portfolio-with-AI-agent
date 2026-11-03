# Blog Manager — API Specification

Nov 4, 2026 · Udit N. · Companion to **Blog Manager Plan.md**

This document lists the REST endpoints the admin Blog Manager page (`/admin/blogs`, design: `Blog Manager.html`) needs. It builds on **New Blog Post API.md**: same base URL, auth, error envelope, date format and optimistic locking. Endpoint numbers continue from that document (1–23), so this one starts at **24**.

---

## 0. Contents

1. What changed from the HTML design
2. Endpoint index (new + reused)
3. Shared objects
4. Endpoints in detail
5. Search — how it works
6. Filter semantics (status × category × search)
7. Status state machine additions
8. Error code catalogue (new codes only)
9. Edge case matrix

---

## 1. What changed from the HTML design

| Design element | Decision |
| --- | --- |
| Stats cards | Four cards: **Total posts**, **Published**, **Drafts**, **Scheduled**. "Pending comments" is removed until the public blog page and comments are built. |
| Moderation banner | Removed (same reason). |
| Tag cloud | Removed. Tags are still matched by search (§5). |
| Status pills | Multi-select. Picking any status turns **All** off (greyed out). Deselecting every status turns **All** back on. |
| Category pills | Single-select (**All** or one category), combined with the status selection using AND. |
| Row click | Opens the post in the editor (`/admin/blogs/{id}/edit`), prefilled and ready to edit. |
| Bulk bar | Only **Archive** and **Delete**. Publish, Schedule and Feature are removed. Publishing and scheduling happen only inside the editor. |
| Row actions | ✎ Edit, ▭ Archive (↺ Restore on archived rows). ✨ AI assist and ↗ Open are hidden until the AI assistant and the public blog page exist. |
| Draft "60 % complete" | There is no data for this. Drafts show word count instead ("Draft · 1,240 words"). |
| Stats column | Shows views only. ★ and comments are added with the public blog page. |

---

## 2. Endpoint index

**4 new endpoints**, plus 4 existing endpoints the page reuses unchanged.

| # | Method | Path | Used by |
| --- | --- | --- | --- |
| **J. Blog Manager (new)** |
| 24 | GET | `/admin/blogs` | Table, pills (facet counts), search, sort, pagination |
| 25 | GET | `/admin/blogs/stats` | The four stats cards |
| 26 | POST | `/admin/blogs/bulk` | Bulk bar → Archive / Delete, and the row ▭ Archive button (one id) |
| 27 | POST | `/admin/blogs/{post_id}/unarchive` | ↺ Restore on an archived row, and "Restore to drafts" in the read-only editor |
| **Reused, already built** |
| 3 | GET | `/admin/blogs/{post_id}` | Row click → editor loads the post (no change) |
| 18 | GET | `/admin/blog-categories` | Category pill names and order (already returns `post_count`) |
| — | GET | `/me` | Who chip |
| 8, 9 | POST / PUT | `/admin/blogs/{post_id}/publish`, `/schedule` | Only from inside the editor — not from the manager |

Not reused: `GET /admin/projects`, `POST /admin/projects/bulk` (projects only; their pagination uses `page_size`, the blog API uses `limit`). The project bulk endpoint is the **pattern** for #26 (ownership check, per-action branching), but #26 returns per-item results because blog posts have per-post rules (see §4.3).

Route order: register `GET /stats` and `POST /bulk` **before** `/{post_id}` in `blogs.py`, next to `slug-check` and `editor-config`. `post_id` is typed `uuid.UUID`, so it can't shadow them anyway.

---

## 3. Shared objects

### 3.1 `PostListItem` — one row of the table

```json
{
  "id": "6f1c…",
  "title": "Building Jerry: a study in style RAG",
  "slug": "building-jerry-style-rag",
  "excerpt": "How to make a frontier LLM sound like you…",
  "status": "published",
  "has_unpublished_changes": true,
  "category": { "id": "…", "name": "AI & Agents", "slug": "ai-agents" },
  "tags": ["langgraph", "rag", "claude", "supabase", "postgres"],
  "cover": { "id": "…", "thumb_url": "https://res.cloudinary.com/…/c_fill,w_128,h_88,f_auto,q_auto/…", "alt": "…" },
  "read_time": 8,
  "word_count": 1840,
  "views": 2104,
  "author": { "id": "…", "name": "Udit N." },
  "version": 14,
  "scheduled_at": null,
  "schedule_error": null,
  "published_at": "2026-05-27T08:18:00Z",
  "archived_at": null,
  "created_at": "2026-05-20T10:02:11Z",
  "updated_at": "2026-05-27T08:18:00Z",
  "search": null
}
```

| Field | Source | Notes |
| --- | --- | --- |
| `title` | `blog_posts.title` | Empty string for an untitled draft; the UI shows "Untitled draft". |
| `excerpt` | `blog_posts.excerpt` | If null, the first 160 characters of `content_text`. |
| `has_unpublished_changes` | `content_hash` ≠ live revision's `content_hash` | Only meaningful when `status = published`. Shown as "Published · edited". |
| `category` | join `blog_categories` | `null` when uncategorized. |
| `tags` | `blog_posts.tags` | All tags; the UI shows 3 and "+N". |
| `cover` | join `media_assets` on `cover_asset_id` | `null` when there is no cover. `thumb_url` is a small Cloudinary crop for the table only — the article cover is never cropped (Plan §8.1). |
| `version` | `blog_posts.version` | Sent back by bulk and unarchive for optimistic locking. |
| `search` | only when `q` is set | `{ "rank": 0.61, "matched": ["title","content"], "snippet": "…<mark>graph</mark>…" }`. `snippet` is HTML with only `<mark>` tags (server-escaped). |

No `content`, `content_html` or `seo` in list items — the list must stay light.

### 3.2 `PostListResponse`

```json
{
  "items": [ /* PostListItem */ ],
  "total": 41, "page": 1, "limit": 20, "total_pages": 3,
  "facets": {
    "status":   { "all": 41, "published": 32, "draft": 7, "scheduled": 2, "archived": 0 },
    "category": { "all": 41, "uncategorized": 0, "<category_id>": 14, "<category_id>": 11 }
  },
  "applied": { "status": ["published","draft"], "category_id": null, "q": "graph", "sort": "relevance", "dir": "desc" }
}
```

Facet counts are **cross-filtered** (§6): status counts apply the current category and search but not the status filter; category counts apply the current status and search but not the category filter. So each pill shows "how many you'd get if you click me".

### 3.3 `BulkResult`

```json
{
  "action": "archive",
  "requested": 3,
  "succeeded": ["id1", "id2"],
  "failed": [
    { "id": "id3", "error": "VERSION_CONFLICT", "message": "This post changed since the list loaded.", "current_version": 9 }
  ]
}
```

---

## 4. Endpoints in detail

### 4.1 · 24 · `GET /admin/blogs` — list, filter, search

| Param | Type | Default | Rules |
| --- | --- | --- | --- |
| `status` | repeatable: `draft` \| `published` \| `scheduled` \| `archived` | none = **All** | `?status=draft&status=scheduled`. Comma form `status=draft,scheduled` also accepted. Unknown value → 422 `VALIDATION_ERROR`. |
| `category_id` | UUID or `none` | none = **All** | `none` = uncategorized posts. Unknown UUID → 200 with zero items (a category deleted in another tab is not an error). |
| `q` | string | — | Trimmed; 2–100 characters, otherwise ignored (< 2) or 422 (> 100). See §5. |
| `sort` | `updated_at` \| `published_at` \| `created_at` \| `title` \| `views` \| `relevance` | `relevance` when `q` is set, else `updated_at` | `relevance` without `q` falls back to `updated_at`. |
| `dir` | `asc` \| `desc` | `desc` (`asc` for `title`) | |
| `page`, `limit` | int | 1, 20 | `limit` clamped to 100 (same as media). `page` past the end → 200 with `items: []` and the real `total_pages`. |

**"All" means every status except `archived`.** Archived posts appear only when the `archived` pill is selected (alone or with others). The `facets.status.all` count follows the same rule.

Ordering always adds `id` as the final tiebreaker so pagination is stable. `published_at` sorting puts nulls (drafts) last. `title` sorting is case-insensitive, with untitled drafts last.

Responses: **200** `PostListResponse` · **401/403** auth · **422** `VALIDATION_ERROR` (`detail.fields` names the bad param).

### 4.2 · 25 · `GET /admin/blogs/stats` — stats cards

```json
{
  "total": 41,
  "published": 32,
  "draft": 7,
  "scheduled": 2,
  "archived": 0,
  "created_this_month": 3,
  "next_scheduled_at": "2026-11-05T03:30:00Z",
  "failed_schedules": 0
}
```

- `total` = `published + draft + scheduled` (archived excluded, matching the **All** pill).
- `created_this_month` drives "▲ 3 this month" (calendar month in `Asia/Kolkata`).
- `next_scheduled_at` drives "next: tomorrow 09:00"; `null` → "nothing queued".
- `failed_schedules` = drafts with a `schedule_error`. If > 0 the Drafts card shows "⚠ N failed to publish" (the scheduler sends a post back to draft when its checklist fails at publish time).
- Not filtered by the pills. One `GROUP BY status` query plus two small aggregates.

### 4.3 · 26 · `POST /admin/blogs/bulk` — Archive / Delete

```json
{ "action": "archive", "items": [ { "id": "…", "version": 14 }, { "id": "…", "version": 3 } ] }
```

- `action`: `archive` | `delete`. Anything else (including `publish`, `schedule`, `feature`) → 422 `VALIDATION_ERROR`.
- `items`: 1–100 entries, ids unique (duplicates are merged). Each carries the `version` from the list row.
- **Partial success.** Each post is checked and changed independently inside one transaction using savepoints. A failing post doesn't roll back the others. The response is **200** with `BulkResult`, even if every item failed. Only malformed requests are 4xx.
- Every post is row-locked (`FOR UPDATE`) and checked against its `version`. A mismatch is a per-item `VERSION_CONFLICT`.
- Ownership: a post whose `author_id` isn't the caller → per-item `FORBIDDEN` (same rule as `GetBlogPost`).

**Archive rules (per post)**

| Current status | Result |
| --- | --- |
| `draft` | → `archived` |
| `published` | → `archived`. The post leaves the public site. `published_at`, `published_revision_id` and slug redirects are kept, so restoring and republishing keeps the original URL and date. |
| `scheduled` | → `archived`, `scheduled_at` cleared (the DB check requires it), activity `blog_unscheduled` logged too. |
| `archived` | per-item `ALREADY_ARCHIVED` (counted as failed, the UI shows it as "skipped"). |

Sets `archived_at = now()`, bumps `version`, logs `blog_archived`.

**Delete rules (per post)** — a hard delete. Revisions and redirects cascade.

| Current status | Result |
| --- | --- |
| `draft`, never published (`published_at IS NULL`) | deleted |
| `archived` | deleted (it has already left the public site) |
| `draft` that was published before (unpublished) | per-item `POST_WAS_PUBLISHED`: "Archive it first." |
| `published` | per-item `POST_WAS_PUBLISHED`: "Archive it first." |
| `scheduled` | per-item `POST_SCHEDULED`: "Open it and unschedule, or archive it." |

Delete also removes the post's `comments` and `reactions` rows (none exist yet, but `comments.blog_id` has no `ON DELETE` rule today and would otherwise fail with a foreign key error → 500; see Plan §5). It logs `blog_deleted` with the title in `entity_title`. The activity row stays, so the feed still says what was deleted.

The single-post `DELETE /admin/blogs/{id}` (endpoint 5) keeps its stricter rule (never-published drafts only), so nothing that uses it changes.

### 4.4 · 27 · `POST /admin/blogs/{post_id}/unarchive`

```json
{ "version": 15 }
```

`archived` → `draft`. Clears `archived_at`, keeps `published_at` and `published_revision_id`, so **Publish** in the editor works like a re-publish (original date kept, `last_published_at` = now; existing D9 behaviour). Logs `blog_updated` with `metadata.action = "unarchived"`.

Responses: **200** `PostDetail` (same object as endpoint 3, so the editor can switch from read-only to editable without a refetch) · **404** `POST_NOT_FOUND` · **409** `NOT_ARCHIVED`, `VERSION_CONFLICT` · **403** `FORBIDDEN`.

It always goes back to `draft`, never straight to `published`. The live page must pass the checklist again (an image may have been deleted while the post was archived).

---

## 5. Search — how it works

**Short answer: keyword search with ranking and typo tolerance, all inside Postgres. No AI or vector search on this page.**

### 5.1 Why not "smart" (semantic) search here

| | Keyword + fuzzy (chosen) | Semantic (embeddings) |
| --- | --- | --- |
| What you type in an admin list | Words you remember from a title, a slug, a tag | Rarely a question or a concept |
| Speed | ~1–5 ms in Postgres, results as you type | Needs an embedding API call per keystroke (100–400 ms + cost) |
| Exact matches | Always shown first | Can rank a loosely related post above the exact title |
| Infrastructure | Indexes already exist (`idx_blog_posts_search`, `idx_blog_posts_title_trgm`) | New embedding column, a job to embed on publish, an API key |
| Explainable | Highlights the matched words | "Why is this here?" |

Semantic search is a good fit for the **public** blog ("posts about making chatbots remember people") and for "related posts". `pgvector` is already installed (Jerry uses it), so it can be added then with a `blog_posts.embedding` column, without changing this endpoint. Plan §11 covers it as a later phase.

### 5.2 What a query matches, and how results are ranked

For `q = "graph memry"` (with a typo):

| Signal | How | Weight |
| --- | --- | --- |
| Title contains the text | `title ILIKE '%graph memry%'` | highest (exact substring) |
| Words in the title | full-text, weight **A** | high |
| Words in subtitle / excerpt | full-text, weight **B** | medium |
| Tag equals a word | `tags && ARRAY['graph','memry']` (normalized like tags) | medium |
| Words in the body | full-text, weight **C** | low |
| Slug contains the text | `slug ILIKE '%graph-memry%'` | medium |
| Typo / partial word in the title | `pg_trgm` `word_similarity(q, title) > 0.4` | catches "memry" → "memory" |

- **Prefix matching for type-ahead:** the last word is searched as a prefix (`graph & memr:*`), so results appear while you're still typing.
- **Stemming:** English config, so "building" matches "build" and "builds".
- **Score:** `rank = 2.0·exact_title + ts_rank_cd(search_vector, query) + 0.6·tag_hit + 0.4·slug_hit + 0.8·title_similarity`. Sort by `rank desc, updated_at desc`.
- **Snippet:** `ts_headline` over excerpt/body with `<mark>` tags, 20 words max. Only computed for the returned page (≤ 20 rows).
- Search works together with the pills. Facet counts reflect the search too.
- Input safety: user text goes through `websearch_to_tsquery` / bound parameters, never string-built SQL. `%` and `_` are escaped for `ILIKE` (existing `_like_escape`).

### 5.3 Client behaviour

- Debounce 250 ms. Fewer than 2 characters → no `q` (full list).
- Cancel the in-flight request when a newer one starts (`AbortController`), so older results never overwrite newer ones.
- ⌘K / Ctrl+K focuses the box. Esc clears it.
- `q` lives in the URL (`?q=graph`) together with the pills, so refresh and the back button keep the view.

---

## 6. Filter semantics

`result = status_filter AND category_filter AND search`

| Status pills selected | Category | SQL | Shown |
| --- | --- | --- | --- |
| All | All | `status <> 'archived'` | every non-archived post |
| All | AI & Agents | `status <> 'archived' AND category_id = :ai` | all AI & Agents posts |
| Published + Draft | AI & Agents | `status IN ('published','draft') AND category_id = :ai` | published or draft AI posts |
| Archived | All | `status = 'archived'` | archived only |
| Draft + Archived | Web Dev | `status IN ('draft','archived') AND category_id = :web` | |
| (user deselects the last status) | — | back to **All** | |

Pill rules in the UI:
- Clicking **All** clears every status pill.
- Clicking a status toggles it. If at least one is on, **All** is greyed (`aria-pressed="false"`, muted style) but still clickable to reset.
- Selecting all four statuses is kept as four pills (it includes archived, so it's not the same as **All**).
- Category is single-select: clicking another category replaces the current one, clicking **All** clears it.
- Any filter change resets `page` to 1 and clears the selection (selected ids may not be in the new list).

---

## 7. Status state machine additions

Adds to New Blog Post API.md §7:

| From | Action | Endpoint | To |
| --- | --- | --- | --- |
| `draft` / `published` / `scheduled` | Archive | 26 | `archived` (`archived_at` set; schedule cleared) |
| `archived` | Restore | 27 | `draft` |
| `archived` | Delete | 26 | — |
| never-published `draft` | Delete | 26 or 5 | — |

`archived` stays read-only in the editor (existing `POST_ARCHIVED` on PATCH, publish, schedule and restore-revision).

---

## 8. Error code catalogue (new)

| HTTP | error | Where |
| --- | --- | --- |
| 200 (per item) | `ALREADY_ARCHIVED`, `POST_WAS_PUBLISHED`, `POST_SCHEDULED`, `VERSION_CONFLICT`, `FORBIDDEN`, `POST_NOT_FOUND` | 26 `failed[]` |
| 409 | `NOT_ARCHIVED` | 27 |
| 409 | `VERSION_CONFLICT` | 27 |
| 422 | `VALIDATION_ERROR` | 24 (bad `status`, `sort`, `dir`, `category_id`, `q` > 100), 26 (bad `action`, 0 or > 100 items) |

---

## 9. Edge case matrix

| # | Case | Behaviour |
| --- | --- | --- |
| M1 | Post edited in another tab after the list loaded, then archived here | Per-item `VERSION_CONFLICT`; toast "1 post changed — refresh and try again"; list refetches. |
| M2 | Select 3 posts, change a filter | Selection cleared (ids may not be visible any more). |
| M3 | Select on page 1, go to page 2 | Selection is kept across pages; the bulk bar shows the total count. "Select all on this page" only selects visible rows. |
| M4 | Bulk delete mixes a published post and two drafts | Two deleted, one failed with "Archive it first". The confirm dialog warns before sending: "1 of 3 can't be deleted — archive it instead?" (the client knows status from the rows). |
| M5 | Delete confirm | Modal lists titles; type `delete` when more than 5 posts or any archived post that was once published. |
| M6 | Archive a scheduled post due in 10 seconds | Row lock: either the scheduler publishes first (then archive moves it from `published` → `archived`) or archive wins and the scheduler skips it (`status <> 'scheduled'`). Never both. |
| M7 | Archive the post currently open in the editor in another tab | That tab's next autosave gets 409 `POST_ARCHIVED` → read-only banner with "Restore to drafts" (27). |
| M8 | Search with only punctuation (`"--"`) | Treated as empty: no `q`, full list. |
| M9 | Search returns nothing | Empty state "No posts match 'xyz' in Published · AI & Agents", with "Clear filters". |
| M10 | Untitled drafts | Title "Untitled draft" in italics; sorted last by title; still found by body search. |
| M11 | Category deleted in another tab while it's the active pill | List returns 0 items; categories refetch; the pill disappears and the filter resets to All. |
| M12 | 100+ posts selected | Bulk bar caps at 100 per request; the client sends batches of 100 and merges the results. |
| M13 | Row click vs checkbox click | Checkbox, action buttons and links stop propagation; only the row body navigates. Ctrl/⌘-click or middle-click opens the editor in a new tab (rows are real links). |
| M14 | Back from the editor | Returns to the same filters, page and scroll position (state is in the URL; scroll restored from `sessionStorage`). |
| M15 | Post published by the scheduler while the list is open | List refetches on window focus and every 60 s while a scheduled post is due in the next hour. |
| M16 | Restore an archived post whose slug was taken while it was archived | Can't happen: archived posts keep their slug, so it stays unique. |

# New Blog Post — API Specification

Nov 3, 2026 · Udit N. · Companion to **New Blog Post Plan.md**

This document lists every REST endpoint the admin blog editor (`New Blog Post.html`) needs, with request and response shapes, error codes and edge cases. It replaces the API sections of `Blog Post Editor — API Spec & Build Prompt.md`, which was written before the live Supabase schema was inspected and before table colours, image galleries, numbered sections and the block registry were in scope.

---

## 0. Contents

1. Conventions (base URL, auth, errors, versioning, dates)
2. Endpoint index
3. Shared objects
4. The content document (what the editor sends as the post body)
5. Endpoints in detail — editor setup, posts, publishing, preview, revisions, taxonomy, content helpers, scheduler
6. Reused media endpoints (already built)
7. Status state machine
8. Error code catalogue
9. Edge case matrix

---

## 1. Conventions

| Topic | Rule |
| --- | --- |
| Base URL | `/api/v1` (mounted in `app/main.py`). All paths below are relative to it. |
| Auth | `Authorization: Bearer <Supabase JWT>`. Every `/admin/*` route uses the existing `get_current_admin` dependency: **401** if the token is missing, invalid or expired, **403** if the user is blocked or `role != 'admin'`. `/internal/*` uses a shared secret instead (see §5.8). |
| Content type | `application/json; charset=utf-8` for every request and response, except media upload (multipart, already built). |
| IDs | UUID v4 strings. A path id that is not a UUID returns **422** (FastAPI path typing), same as projects. |
| Dates | Stored as `timestamptz` in UTC. Responses use `YYYY-MM-DDTHH:MM:SSZ` (same serializer as media). Requests accept any ISO 8601 string **with an offset** (`2026-11-28T09:00:00+05:30`); a naive datetime is **422 `NAIVE_DATETIME`**. The UI displays in `Asia/Kolkata`. |
| Optimistic locking | Every write to a post sends the post's current `version` (integer). The server runs `UPDATE … WHERE id = :id AND version = :version` and bumps `version` by 1. Zero rows updated returns **409 `VERSION_CONFLICT`** with the current version. This is what protects you when the same post is open in two tabs. |
| Idempotency | `POST /admin/blogs` accepts an `Idempotency-Key` header (client-generated UUID). A repeat with the same key within 24 h returns the post created the first time (200) instead of a duplicate. This stops two near-simultaneous autosaves from creating two drafts. |
| Partial updates | `PATCH` only changes the keys present in the body. An explicit `null` clears a nullable field; an omitted key leaves it alone (same `exclude_unset` pattern as `PATCH /admin/media/{id}`). |
| Error envelope | Matches the existing projects/media endpoints: `{"detail": {"error": "UPPER_SNAKE_CODE", "message": "Human readable.", "detail": { …optional context… }}}`. |
| Pagination | `page` (≥ 1, default 1) and `limit` (default 20, clamped to 100) — same as media. Responses carry `total`, `page`, `limit`, `total_pages`. |
| Rate limit | 500 requests/min per admin token. Autosave (at most one request in flight, ~1 per 1.5 s) stays well inside it. Over the limit: **429 `RATE_LIMITED`** with `Retry-After`. |

---

## 2. Endpoint index

23 new endpoints, plus 7 existing endpoints the editor reuses unchanged.

| # | Method | Path | Used by (control in the HTML) |
| --- | --- | --- | --- |
| **A. Editor setup** |
| 1 | GET | `/admin/blogs/editor-config` | Page load: block registry, slash menu, limits, colour palette, code languages, embed providers, timezone, site URL |
| **B. Posts** |
| 2 | POST | `/admin/blogs` | First autosave on `/admin/blogs/new` (lazy create) |
| 3 | GET | `/admin/blogs/{post_id}` | Page load of `/admin/blogs/{id}/edit` |
| 4 | PATCH | `/admin/blogs/{post_id}` | Every autosave (Enter key, typing pause, blur) and every rail field |
| 5 | DELETE | `/admin/blogs/{post_id}` | ⋯ menu → "Delete draft" |
| 6 | GET | `/admin/blogs/slug-check` | Slug line "✎ edit" |
| **C. Publishing** |
| 7 | GET | `/admin/blogs/{post_id}/checklist` | "Before publish" panel refresh |
| 8 | POST | `/admin/blogs/{post_id}/publish` | **↗ Publish** / **Update** button |
| 9 | PUT | `/admin/blogs/{post_id}/schedule` | **📅 Schedule** / Reschedule |
| 10 | DELETE | `/admin/blogs/{post_id}/schedule` | Schedule popover → Unschedule |
| 11 | POST | `/admin/blogs/{post_id}/unpublish` | ⋯ menu → Unpublish |
| 12 | POST | `/admin/blogs/{post_id}/discard-changes` | ⋯ menu → Discard unpublished changes |
| **D. Preview** |
| 13 | GET | `/admin/blogs/{post_id}/preview` | **⌕ Preview** (opens `/admin/blogs/{id}/preview`) |
| **E. Revisions** |
| 14 | POST | `/admin/blogs/{post_id}/revisions` | **Save draft** button, ⌘S / Ctrl+S |
| 15 | GET | `/admin/blogs/{post_id}/revisions` | History drawer |
| 16 | GET | `/admin/blogs/{post_id}/revisions/{revision_id}` | History drawer → view a revision |
| 17 | POST | `/admin/blogs/{post_id}/revisions/{revision_id}/restore` | History drawer → Restore |
| **F. Taxonomy** |
| 18 | GET | `/admin/blog-categories` | Category select |
| 19 | POST | `/admin/blog-categories` | Category select → "+ New category" |
| 20 | GET | `/admin/blog-tags` | Tag chip autocomplete |
| **G. Content helpers** |
| 21 | POST | `/admin/blogs/embeds/resolve` | Toolbar ⎘ Embed, slash `/embed` |
| 22 | GET | `/admin/blogs/link-targets` | Link popover → search your own posts and projects |
| **H. Scheduler** |
| 23 | POST | `/internal/blogs/publish-due` | Cron trigger (no UI) |
| **I. Reused, already built** |
| — | GET | `/me` | Who chip (avatar, name, role) |
| — | GET | `/admin/media?folder=&resource_type=&search=` | "Browse Cloudinary library" modal (cover, inline image, gallery, video, OG) |
| — | POST | `/admin/media/upload` (multipart) | Upload from device |
| — | POST | `/admin/media/import-url` | Add a YouTube video (and import images by URL) |
| — | GET | `/admin/media/{asset_id}` | Re-fetch an asset after alt text edit |
| — | PATCH | `/admin/media/{asset_id}` | Edit alt text from the image node |
| — | GET | `/admin/media/{asset_id}/usage` | Already scans blog cover, OG and content; extended to scan published revisions (Plan §6.3) |

Route-order rule (same as `projects.py`): register `editor-config`, `slug-check`, `embeds/resolve` and `link-targets` **before** `/{post_id}`. The `post_id` param is typed `uuid.UUID`, so it can't shadow them anyway.

---

## 3. Shared objects

### 3.1 `PostWritable` — the fields the editor can set

Every field is optional on `PATCH`. All are nullable except `tags` and `content`.

```json
{
  "title": "Building Jerry: a study in style RAG",
  "subtitle": "How to make a frontier LLM sound like you — without training a model from scratch.",
  "slug": "building-jerry-style-rag",
  "slug_locked": true,
  "content": { "type": "doc", "schema_version": 1, "content": [ "…see §4…" ] },
  "excerpt": "How to make a frontier LLM sound like you — without training a model from scratch. Three layers, no fine-tuning.",
  "cover_asset_id": "0b6f…",
  "og_asset_id": null,
  "category_id": "7c1e…",
  "tags": ["langgraph", "rag", "claude", "pgvector"],
  "allow_comments": true,
  "seo": {
    "meta_title": "Building Jerry: a study in style RAG · Udit N.",
    "meta_description": "A frontier LLM wrapped in voice profile + style RAG + graph memory…",
    "canonical_url": null
  }
}
```

| Field | Type | Rules | Notes |
| --- | --- | --- | --- |
| title | string | trimmed; 0–150 chars while drafting; **10–100 to publish** | Never contains newlines. |
| subtitle | string \| null | ≤ 200 chars; ideal ≤ 160 | Rendered under the title. |
| slug | string | normalized to `^[a-z0-9]+(-[a-z0-9]+)*$`, 3–80 chars; not reserved | Ignored unless `slug_locked` is true or is sent together with `slug_locked: true`. |
| slug_locked | bool | — | `false` = server re-derives slug from title on every save (drafts only — see §9 B4). |
| content | object | §4; ≤ 1 MB serialized; ≤ 5,000 nodes | The only body format. The client never sends HTML. |
| excerpt | string \| null | ≤ 300 chars while drafting; **≤ 200 to publish**; warning below 80 | Card text and meta-description fallback. |
| cover_asset_id | uuid \| null | must be an **image** asset that exists | Server also writes `cover_image_url`. |
| og_asset_id | uuid \| null | must be an **image** asset | Falls back to the cover when null. Server writes `og_image_url`. |
| category_id | uuid \| null | must exist | Required to publish. |
| tags | string[] | 0–8 items; each normalized to lowercase kebab-case, 2–30 chars; duplicates removed | Order is kept. |
| allow_comments | bool | — | Column already exists (default true). |
| seo.meta_title | string \| null | ≤ 70 chars; warning outside 30–60 | Fallback: `"{title} · Udit N."`. |
| seo.meta_description | string \| null | ≤ 200 chars; warning outside 120–160 | Fallback: excerpt. |
| seo.canonical_url | string \| null | absolute `https://` URL | Fallback: `https://uditnarayana.dev/blog/{slug}`. |

**Not writable** (silently ignored if sent, never an error, so an old client can't break): `id`, `status`, `visibility` (always `public` — removed from the UI, see Plan §3.13), `views`, `author_id`, `published_at`, `scheduled_at` (use endpoint 9), `content_html`, `version` is read from the body only as the lock value.

### 3.2 `PostDetail` — returned by create, GET, publish, schedule, unschedule, unpublish, discard, restore

```json
{
  "id": "9f2c5b1e-…",
  "version": 14,
  "title": "Building Jerry: a study in style RAG",
  "subtitle": "How to make a frontier LLM sound like you — without training a model from scratch.",
  "slug": "building-jerry-style-rag",
  "slug_locked": true,
  "content": { "type": "doc", "schema_version": 1, "content": [] },
  "excerpt": "How to make a frontier LLM sound like you…",
  "cover": MediaRef | null,
  "og_image": MediaRef | null,
  "category": { "id": "7c1e…", "name": "AI & Agents", "slug": "ai-agents" } | null,
  "tags": ["langgraph", "rag", "claude", "pgvector"],
  "allow_comments": true,
  "seo": { "meta_title": null, "meta_description": "…", "canonical_url": null },
  "seo_effective": {
    "meta_title": "Building Jerry: a study in style RAG · Udit N.",
    "meta_description": "A frontier LLM wrapped in voice profile…",
    "canonical_url": "https://uditnarayana.dev/blog/building-jerry-style-rag",
    "og_image_url": "https://res.cloudinary.com/…/c_fill,w_1200,h_630/…"
  },
  "status": "draft",
  "status_label": "Draft",
  "scheduled_at": null,
  "published_at": null,
  "last_published_at": null,
  "has_unpublished_changes": false,
  "public_url": null,
  "schedule_error": null,
  "stats": { "word_count": 580, "reading_time_min": 3, "block_count": 12, "image_count": 2 },
  "checklist": Checklist,
  "author": { "id": "…", "name": "Udit N.", "avatar_url": null },
  "created_at": "2026-11-03T08:59:00Z",
  "updated_at": "2026-11-03T09:17:12Z"
}
```

- `status` ∈ `draft | scheduled | published | archived`. The DB enum also has `review`; the editor never sets it and reads it as `draft`.
- `status_label` is ready-made text for the status pill: `Draft`, `Scheduled · 28 Nov, 9:00 AM`, `Published`, `Published · unpublished changes`, `Archived`.
- `has_unpublished_changes` is `true` only when `status = published` and the working copy's `content_hash` differs from the live revision's hash.
- `public_url` is set only while published.
- `schedule_error` holds the reason the last automatic publish failed (see endpoint 23), and is cleared on the next successful schedule or publish.
- `content_html` is **not** in PostDetail. The editor doesn't need it; preview (13) returns it.

### 3.3 `PostSaveResult` — the light response to PATCH (autosave)

```json
{
  "id": "9f2c…",
  "version": 15,
  "updated_at": "2026-11-03T09:17:14Z",
  "slug": "building-jerry-style-rag",
  "slug_adjusted": false,
  "stats": { "word_count": 584, "reading_time_min": 3, "block_count": 12, "image_count": 2 },
  "has_unpublished_changes": false,
  "checklist": Checklist,
  "warnings": []
}
```

`slug_adjusted: true` means the server de-duplicated an auto slug (e.g. `building-jerry-2`). `warnings` carries non-blocking notes like `{"code": "LINK_TO_DRAFT", "path": "content[14].content[0].marks[0]", "message": "Links to an unpublished post"}`.

### 3.4 `MediaRef` — compact asset view embedded in posts

```json
{
  "id": "0b6f…",
  "url": "https://res.cloudinary.com/<cloud>/image/upload/v1730/blog/covers/jerry-cover.webp",
  "public_id": "blog/covers/jerry-cover",
  "resource_type": "image",
  "source_type": "cloudinary",
  "width": 2400, "height": 1350,
  "alt_text": "Diagram of Jerry's three-layer wrapper",
  "thumbnail_url": "https://res.cloudinary.com/…/c_fill,w_320,h_180/…"
}
```

For YouTube assets `source_type` is `youtube`, `url` is the watch URL, plus `external_id`, `video_title` and `video_duration_seconds`.

### 3.5 `Checklist`

```json
{
  "can_publish": false,
  "blocker_count": 1,
  "warning_count": 2,
  "items": [
    { "key": "title", "label": "Title & subtitle", "level": "blocker", "passed": true, "message": null },
    { "key": "cover", "label": "Cover image missing", "level": "warning", "passed": false,
      "message": "Posts without a cover get a plain card on the blog index." },
    { "key": "image_alt", "label": "Every image has alt text", "level": "blocker", "passed": false,
      "message": "2 images are missing alt text.", "paths": ["content[18]", "content[22].attrs.images[1]"] }
  ]
}
```

| key | level | Passes when |
| --- | --- | --- |
| `title` | blocker | 10–100 chars |
| `slug` | blocker | valid, not reserved, not used by another post |
| `category` | blocker | `category_id` set and the category still exists |
| `excerpt` | blocker | present, ≤ 200 chars |
| `body` | blocker | ≥ 50 words of body text |
| `image_alt` | blocker | every `image` node and every gallery item has non-empty alt (≥ 3 chars) |
| `media_exists` | blocker | every referenced asset id (cover, OG, image, gallery, video) still exists in `media_assets` |
| `embeds_valid` | blocker | every `embed` node's URL still passes the provider allowlist |
| `empty_blocks` | warning | no empty headings, empty table, empty code block or empty list items |
| `cover` | warning | cover set |
| `og_image` | warning | OG set, or a cover exists to fall back on (message says "using cover") |
| `tags` | warning | ≥ 1 tag |
| `excerpt_length` | warning | 80–200 chars |
| `meta_title_length` | warning | effective meta title 30–60 chars |
| `meta_description_length` | warning | effective meta description 120–160 chars |
| `heading_order` | warning | no H3 before the first H2 |

`can_publish` = every blocker passed. Warnings never block publishing or scheduling. The mock's "Spelling pass" item is dropped because nothing can verify it (Plan §3.20).

### 3.6 `RevisionSummary`

```json
{ "id": "…", "kind": "publish", "label": "Published", "word_count": 580,
  "created_by": { "id": "…", "name": "Udit N." }, "created_at": "…", "is_live": true }
```

`kind` ∈ `publish | manual | restore`.

### 3.7 `PublicPostPayload` — what preview returns, and what the future public endpoint returns

The preview (13) and the future public `GET /blogs/{slug}` return the same shape, so the preview is exactly what readers will see.

```json
{
  "title": "…", "subtitle": "…", "slug": "…",
  "url": "https://uditnarayana.dev/blog/building-jerry-style-rag",
  "cover": { "url": "…", "alt": "…", "width": 2400, "height": 1350,
             "srcset": "…w_640 640w, …w_1280 1280w, …w_1920 1920w" } | null,
  "category": { "name": "AI & Agents", "slug": "ai-agents", "url": "/blog/category/ai-agents" },
  "tags": [{ "name": "langgraph", "url": "/blog/tag/langgraph" }],
  "author": { "name": "Udit N.", "avatar_url": null },
  "published_at": "2026-11-28T03:30:00Z" | null,
  "updated_at": "…",
  "reading_time_min": 3, "word_count": 580,
  "toc": [ { "id": "the-trade-offs-no-one-talks-about", "text": "The trade-offs no one talks about", "level": 2, "number": null },
           { "id": "the-voice-profile", "text": "The voice profile", "level": 3, "number": "1" } ],
  "content_html": "<p>Jerry is …</p><h2 id=\"…\">…</h2>…",
  "head": {
    "title": "Building Jerry: a study in style RAG · Udit N.",
    "meta": [ { "name": "description", "content": "…" },
              { "property": "og:type", "content": "article" },
              { "property": "og:title", "content": "…" },
              { "property": "og:description", "content": "…" },
              { "property": "og:image", "content": "…1200x630…" },
              { "property": "og:url", "content": "…" },
              { "property": "article:published_time", "content": "…" },
              { "property": "article:section", "content": "AI & Agents" },
              { "property": "article:tag", "content": "langgraph" },
              { "name": "twitter:card", "content": "summary_large_image" } ],
    "links": [ { "rel": "canonical", "href": "…" } ],
    "json_ld": { "@context": "https://schema.org", "@type": "BlogPosting", "headline": "…", "image": ["…"],
                 "datePublished": "…", "dateModified": "…", "author": { "@type": "Person", "name": "Udit N." },
                 "articleSection": "AI & Agents", "keywords": "langgraph, rag, claude, pgvector",
                 "wordCount": 580, "mainEntityOfPage": "…" }
  }
}
```

---

## 4. The content document

The post body is one JSON document (TipTap / ProseMirror format) stored in `blog_posts.content`. This is how the website knows that "The trade-offs no one talks about" is a heading and the text under it is a paragraph: each piece of text lives in a typed node.

```json
{
  "type": "doc",
  "schema_version": 1,
  "content": [
    { "type": "paragraph", "content": [ { "type": "text", "text": "Jerry is Udit's AI-powered client representative…" } ] },
    { "type": "heading", "attrs": { "level": 2 }, "content": [ { "type": "text", "text": "The trade-offs no one talks about" } ] },
    { "type": "paragraph", "content": [ { "type": "text", "text": "A 500M-parameter model…" } ] }
  ]
}
```

The server validates the document against the allowlist below on every create, PATCH and restore. **Anything not listed is rejected with 422 `INVALID_CONTENT`** and a JSON path. This allowlist is what makes the server-rendered HTML safe. The allowlist comes from the block registry (Plan §4.3), and endpoint 1 returns it, so adding a new block type later means adding one registry entry on each side.

### 4.1 Block nodes

| Node | Attributes (type · rule) | Allowed children | Renders as |
| --- | --- | --- | --- |
| `paragraph` | `align`: `left`\|`center`\|`right` (default left) | inline | `<p>` |
| `heading` | `level`: **2 \| 3 \| 4**; `numbered`: bool (default false); `id`: server-generated, read-only | inline (text, marks; no images) — ≤ 150 chars | `<h2/3/4 id>`; numbered headings get an auto number (§4.4) |
| `bulletList` | — | `listItem`+ | `<ul>` |
| `orderedList` | `start`: int ≥ 1 (default 1); `style`: `decimal`\|`lower-alpha`\|`lower-roman` (default decimal; nested levels cycle automatically) | `listItem`+ | `<ol>` |
| `listItem` | — | paragraph first, then any of: paragraph, bulletList, orderedList, codeBlock, image, callout, blockquote | `<li>` |
| `blockquote` | `attribution`: string ≤ 120 (e.g. "alpha tester, week 2"); `cite_url`: https URL \| null; `variant`: `default`\|`pull` | paragraph+ | `<figure><blockquote>…</blockquote><figcaption>— …</figcaption></figure>` |
| `callout` | `variant`: `note` (yellow, default) \| `info` \| `tip` \| `warning` \| `danger`; `icon`: one emoji or symbol ≤ 4 chars (default per variant, e.g. ✏︎); `title`: string ≤ 120 \| null | paragraph, bulletList, orderedList, codeBlock | `<aside class="callout callout--note" role="note">` |
| `codeBlock` | `language`: one of the editor-config list, default `plaintext`; `filename`: ≤ 80 \| null; `show_line_numbers`: bool; `highlight_lines`: string like `"2,4-6"` \| null | text only, ≤ 20,000 chars, no marks | `<figure class="code"><figcaption>filename · Python</figcaption><pre><code class="language-python">` with copy button |
| `table` | `header_row`: bool (default true); `header_col`: bool (default false); `header_style`: palette token (default `ink`); `striped`: bool; `border`: `grid`\|`rows`\|`none`; `col_widths`: int[] \| null (px, one per column) | `tableRow`+ — **1–200 rows, 1–20 columns**, rectangular after spans | `<div class="table-wrap"><table>` (scrolls sideways on mobile) |
| `tableRow` | — | `tableHeader` \| `tableCell` | `<tr>` |
| `tableHeader` / `tableCell` | `colspan`, `rowspan`: 1–20; `background`: palette token \| null; `align`: `left`\|`center`\|`right` | paragraph+, bulletList, orderedList | `<th>` / `<td>` |
| `image` | `asset_id`: uuid (required); `public_id`: string (required); `src`: Cloudinary URL (required); `alt`: string ≤ 250 (required to publish); `caption`: ≤ 300 \| null; `width`, `height`: int; `size`: `normal`\|`wide`\|`full`; `link_href`: URL \| null | — | `<figure><img srcset loading="lazy" decoding="async"><figcaption>` |
| `imageGallery` | `items`: **2–20** × `{asset_id, public_id, src, alt, caption?, width, height}`; `height`: `sm` (240px) \| `md` (360px, default) \| `lg` (480px); `caption`: ≤ 300 \| null | — | Horizontal scroll strip with CSS scroll-snap, ← → buttons, swipe on touch, click opens a lightbox |
| `video` | `source`: `cloudinary`\|`youtube`; `asset_id`: uuid (required); `src`: Cloudinary video URL (cloudinary) or `embed_url` (youtube, `https://www.youtube-nocookie.com/embed/{id}`); `external_id`: YouTube id \| null; `watch_url`: `https://www.youtube.com/watch?v={id}` \| null; `poster_url`; `title`; `duration_seconds`; `caption` ≤ 300 \| null; `start_seconds`: int \| null | — | Cloudinary: `<video controls preload="metadata" playsinline poster>`. YouTube: a click-to-load player that plays **on the page**, plus a "Watch on YouTube ↗" link under it |
| `embed` | `provider`: from the editor-config list; `original_url`; `embed_url` (must equal what endpoint 21 returned for `original_url`); `title`; `height`: 200–900 | — | sandboxed `<iframe loading="lazy" sandbox="allow-scripts allow-same-origin allow-popups">` |
| `horizontalRule` | — | — | `<hr>` |

### 4.2 Inline nodes and marks

| Name | Kind | Attributes | Shortcut |
| --- | --- | --- | --- |
| `text` | node | `text` (non-empty) | — |
| `hardBreak` | node | — | Shift+Enter inside a paragraph |
| `bold` | mark | — | Ctrl/⌘+B |
| `italic` | mark | — | Ctrl/⌘+I |
| `underline` | mark | — | Ctrl/⌘+U |
| `strike` | mark | — | Ctrl/⌘+Shift+X |
| `code` | mark | — | Ctrl/⌘+E or backticks |
| `highlight` | mark | `color`: palette token, default `highlight` (yellow) | Ctrl/⌘+Shift+H |
| `link` | mark | `href`: `https://…`, `http://…`, `mailto:…`, or site-relative `/…` or `#heading-id`; `target`: `_blank` \| null; `internal`: `{type: "blog"\|"project", id: uuid}` \| null | Ctrl/⌘+K |

Rejected link schemes: `javascript:`, `data:`, `vbscript:`, `file:` and anything else → **422 `INVALID_LINK`**. External links render with `rel="noopener noreferrer"`. Internal links (`internal` set) are re-resolved at render time, so they keep working if the target's slug changes.

### 4.3 Colour palette tokens

Tables, cells, callouts and highlights store **token names, not hex codes**. If you change the theme or add dark mode later, every post follows automatically. Endpoint 1 returns the palette with hex values for the editor's swatches.

| Token | Light hex | Typical use |
| --- | --- | --- |
| `ink` | `#21201c` (text `#f5f1e8`) | Default table header |
| `paper` | `#f5f1e8` | Plain |
| `paper-dark` | `#ebe4d3` | Subtle header, zebra stripe |
| `highlight` | `#f4e07a` | Yellow callout, highlighted text |
| `accent` | `#c1432a` (text white) | Strong header |
| `accent-soft` | `#c1432a22` | Emphasised cell or row |
| `ok-soft` | `#6aa84f33` | "Good" cell |
| `warn-soft` | `#f4b03a33` | "Caution" cell |
| `info-soft` | `#2a5fa322` | Info callout |

### 4.4 Numbering (never typed, never stored)

- **Ordered lists:** item numbers are computed from position. Inserting, deleting or reordering items renumbers them; `start` is the only stored number.
- **Numbered headings:** a heading with `numbered: true` gets its number from its position among numbered headings of the **same level under the same parent heading**. For example, the three `level: 3, numbered: true` headings under "Three layers, no training" render as **1.**, **2.**, **3.**, and any paragraphs, code blocks or tables between them don't affect the count. A new H2 restarts the count. The number appears in the HTML and in `toc[].number`, but never in the stored text.

### 4.5 Server-side limits (422 `CONTENT_LIMIT_EXCEEDED` with `detail.limit`)

| Limit | Value |
| --- | --- |
| Serialized JSON | 1 MB (larger → **413 `CONTENT_TOO_LARGE`**) |
| Total nodes | 5,000 |
| Nesting depth | 8 |
| Text in one node | 20,000 chars |
| Tables per post | 30 |
| Galleries per post | 20 |
| Videos + embeds per post | 20 |

---

## 5. Endpoints in detail

### 5.1 Editor setup

#### 1 · `GET /admin/blogs/editor-config`

Loads everything the editor needs that isn't the post, once per page load (cacheable for 5 min with `ETag`).

**Response 200**
```json
{
  "site_url": "https://uditnarayana.dev",
  "blog_base_path": "/blog",
  "timezone": "Asia/Kolkata",
  "title_suffix": " · Udit N.",
  "content_schema_version": 1,
  "limits": {
    "title": [10, 100], "subtitle_max": 200, "excerpt": [80, 200], "excerpt_hard_max": 300,
    "meta_title": [30, 60], "meta_description": [120, 160],
    "tags_max": 8, "tag_length": [2, 30], "min_words": 50,
    "slug_length": [3, 80], "schedule_min_lead_minutes": 5, "schedule_max_days_ahead": 365,
    "content_max_bytes": 1048576, "table_max_rows": 200, "table_max_cols": 20,
    "gallery_items": [2, 20], "code_max_chars": 20000
  },
  "blocks": [
    { "type": "heading", "label": "Heading", "icon": "H", "group": "text",
      "variants": [ { "key": "h2", "label": "Section heading", "attrs": { "level": 2 }, "shortcut": "## " },
                    { "key": "h3", "label": "Sub-heading", "attrs": { "level": 3 }, "shortcut": "### " },
                    { "key": "h3n", "label": "Numbered sub-heading", "attrs": { "level": 3, "numbered": true }, "shortcut": "#. " } ],
      "slash_keywords": ["h2", "h3", "title", "section"], "toolbar": true, "enabled": true },
    { "type": "callout", "label": "Callout", "icon": "⚑", "group": "text",
      "variants": [ { "key": "note", "label": "Note (yellow)" }, { "key": "info", "label": "Info" },
                    { "key": "tip", "label": "Tip" }, { "key": "warning", "label": "Warning" }, { "key": "danger", "label": "Danger" } ],
      "slash_keywords": ["note", "callout", "box", "yellow"], "toolbar": true, "enabled": true },
    "… one entry per node in §4.1 …"
  ],
  "marks": ["bold", "italic", "underline", "strike", "code", "highlight", "link"],
  "palette": [ { "token": "ink", "label": "Ink", "bg": "#21201c", "fg": "#f5f1e8" }, "…" ],
  "code_languages": [ { "id": "python", "label": "Python" }, { "id": "typescript", "label": "TypeScript" },
                      { "id": "javascript", "label": "JavaScript" }, { "id": "tsx", "label": "TSX" },
                      { "id": "bash", "label": "Bash" }, { "id": "sql", "label": "SQL" }, { "id": "json", "label": "JSON" },
                      { "id": "yaml", "label": "YAML" }, { "id": "html", "label": "HTML" }, { "id": "css", "label": "CSS" },
                      { "id": "go", "label": "Go" }, { "id": "rust", "label": "Rust" }, { "id": "java", "label": "Java" },
                      { "id": "dockerfile", "label": "Dockerfile" }, { "id": "diff", "label": "Diff" },
                      { "id": "plaintext", "label": "Plain text" } ],
  "embed_providers": [ { "id": "codepen", "label": "CodePen", "hosts": ["codepen.io"] },
                       { "id": "codesandbox", "label": "CodeSandbox", "hosts": ["codesandbox.io"] },
                       { "id": "gist", "label": "GitHub Gist", "hosts": ["gist.github.com"] },
                       { "id": "figma", "label": "Figma", "hosts": ["figma.com", "www.figma.com"] },
                       { "id": "loom", "label": "Loom", "hosts": ["loom.com", "www.loom.com"] } ],
  "media_folders": { "cover": "blog/covers", "inline": "blog/inline", "gallery": "blog/inline",
                     "video": "blog/videos", "og": "system/og-images" },
  "upload": { "image_formats": ["jpg", "jpeg", "png", "webp", "gif", "avif"], "image_max_bytes": 10485760,
              "video_formats": ["mp4", "webm", "mov"], "video_max_bytes": 209715200,
              "cover_min_width": 1200, "og_recommended": [1200, 630] },
  "reserved_slugs": ["new", "preview", "edit", "admin", "api", "category", "tag", "tags", "page", "rss", "feed", "sitemap", "search", "drafts"]
}
```

Only `blocks` with `enabled: true` show in the toolbar and slash menu. The server rejects disabled types on save, so turning a block off is a config change.

Errors: 401, 403.

---

### 5.2 Posts

#### 2 · `POST /admin/blogs` — create draft (lazy)

Called by the **first** autosave on `/admin/blogs/new` that has a title or some body text. Opening "New post" and leaving never creates an empty draft. On 201 the client does `history.replaceState` to `/admin/blogs/{id}/edit`.

Headers: `Idempotency-Key: <uuid>` (recommended).

**Request** — any subset of `PostWritable`:
```json
{ "title": "Building Jerry", "content": { "type": "doc", "schema_version": 1, "content": [] } }
```

**Response 201** — `PostDetail` with `status: "draft"`, `version: 1`, slug derived from the title (or `untitled-<6 chars>` if no title yet). Writes activity `blog_created`.
**Response 200** — same body, when the `Idempotency-Key` was already used.

| Status | error | When |
| --- | --- | --- |
| 422 | `EMPTY_POST` | No title and no body text. |
| 422 | `INVALID_CONTENT` | Node, mark or attribute not in the allowlist. `detail.path`, `detail.reason`. |
| 422 | `INVALID_LINK` | Disallowed link scheme. |
| 422 | `VALIDATION_ERROR` | Field-level failure (`detail.fields`: `{field: message}`). |
| 422 | `CATEGORY_NOT_FOUND` / `MEDIA_NOT_FOUND` / `MEDIA_TYPE_MISMATCH` | Bad `category_id`, asset id, or a video used as a cover. |
| 413 | `CONTENT_TOO_LARGE` | Over 1 MB. |
| 409 | `IDEMPOTENCY_KEY_REUSED` | Same key, different body. |

#### 3 · `GET /admin/blogs/{post_id}`

**Response 200** — `PostDetail`.
Errors: **404 `POST_NOT_FOUND`**; **403 `FORBIDDEN`** if another admin is the author (same rule as projects).

If the stored document's `schema_version` is older than the current one, the server upgrades it in memory before returning and saves the upgrade on the next PATCH (Plan §4.4).

#### 4 · `PATCH /admin/blogs/{post_id}` — autosave and every rail field

**Request** — `version` plus any subset of `PostWritable`:
```json
{ "version": 14, "content": { "type": "doc", "schema_version": 1, "content": [ "…" ] } }
```
```json
{ "version": 15, "tags": ["langgraph", "rag", "claude", "pgvector", "supabase"] }
```

On every PATCH the server:
1. Validates the fields and the content allowlist.
2. Re-renders `content_html`, `content_text`, heading ids, numbers, stats and `content_hash`.
3. Re-derives the slug while `slug_locked` is false and the post has never been published.
4. Bumps `version`.
5. Returns `PostSaveResult`.

Sending a field with the same value is a no-op for that field, but `version` still bumps, so the response's version is always the one to send next.

**Response 200** — `PostSaveResult` (§3.3).

| Status | error | When |
| --- | --- | --- |
| 409 | `VERSION_CONFLICT` | `version` is stale. `detail: {current_version, updated_at}`. The editor shows "Edited in another tab — Reload / Keep mine". "Keep mine" re-sends with `current_version`. |
| 409 | `SLUG_TAKEN` | Locked slug already used. `detail.suggestion: "building-jerry-2"`. |
| 422 | `RESERVED_SLUG` | e.g. `new`, `admin`. |
| 422 | `INVALID_CONTENT`, `INVALID_LINK`, `CONTENT_LIMIT_EXCEEDED`, `VALIDATION_ERROR`, `CATEGORY_NOT_FOUND`, `MEDIA_NOT_FOUND`, `MEDIA_TYPE_MISMATCH` | As in endpoint 2. |
| 413 | `CONTENT_TOO_LARGE` | — |
| 409 | `POST_ARCHIVED` | Archived posts are read-only; restore from Blog Manager first. |
| 404 / 403 | — | — |

Edits to a **scheduled** post are allowed and are what gets published at the scheduled time. Edits to a **published** post only change the working copy (`has_unpublished_changes` becomes true) until you press **Update**.

#### 5 · `DELETE /admin/blogs/{post_id}`

Hard-deletes a post that has **never been published** (`published_at IS NULL`), together with its revisions. Writes `blog_deleted`.

**Request:** `?version=17` (query param, because DELETE has no body).
**Response 204**.

| Status | error | When |
| --- | --- | --- |
| 409 | `POST_WAS_PUBLISHED` | It has been live at least once (it may have comments, links or search index entries). Unpublish it and archive it from Blog Manager instead. |
| 409 | `POST_SCHEDULED` | Unschedule first. |
| 409 | `VERSION_CONFLICT` | — |

Media assets are not deleted. They remain in the library and stop showing this post in "Used in".

#### 6 · `GET /admin/blogs/slug-check?slug=&exclude_id=`

Same behaviour as `/admin/projects/slug-check`. Debounce 400 ms on the client.

**Response 200**
```json
{ "input": "Building Jerry!!", "slug": "building-jerry", "available": false,
  "reason": "taken", "suggested": "building-jerry-2" }
```
`reason` ∈ `null | taken | reserved | redirect_reserved | too_short | too_long | invalid`. `redirect_reserved` means the slug is an old slug of another post that still redirects (§9 B5).

Errors: **400 `MISSING_PARAM`** if `slug` is absent.

---

### 5.3 Publishing

#### 7 · `GET /admin/blogs/{post_id}/checklist`

**Response 200** — `Checklist` (§3.5). The same rule list runs in the browser for live ticks, but this server copy is the one publish and the scheduler enforce. The editor calls it after saves that touch media or links, and before opening the Publish or Schedule popover.

#### 8 · `POST /admin/blogs/{post_id}/publish` — Publish and Update

**Request**
```json
{ "version": 21 }
```

The server, in one transaction:
1. Flushes nothing (the client must PATCH first and send the resulting version).
2. Locks the row with `FOR UPDATE`.
3. Runs the checklist.
4. Writes a `publish` revision (snapshot + `content_html`).
5. Sets `published_revision_id`, `status = 'published'` and `published_at` (first publish only; the existing `set_published_at` trigger keeps the original date on re-publish), sets `last_published_at = now()`, and clears `scheduled_at` and `schedule_error`.
6. If the slug changed since the previous live revision, inserts `blog_slug_redirects(old_slug → post)`.
7. Writes activity `blog_published` (first time) or `blog_updated` (Update).

This works from `draft`, from `scheduled` (publish now, and the schedule is cancelled), and from `published` with changes (Update).

**Response 200** — `PostDetail` with `status: "published"`, `public_url`, `has_unpublished_changes: false`.

| Status | error | When |
| --- | --- | --- |
| 422 | `CHECKLIST_FAILED` | Any blocker fails. `detail.checklist` = full `Checklist`. The UI opens the checklist panel and scrolls to the first failing block using `paths`. |
| 409 | `NO_CHANGES` | Already published and the hash is unchanged. The UI disables Update in this state, so this only happens on a race. |
| 409 | `VERSION_CONFLICT` | — |
| 409 | `POST_ARCHIVED` | — |

#### 9 · `PUT /admin/blogs/{post_id}/schedule` — Schedule and Reschedule

**Request**
```json
{ "version": 21, "scheduled_at": "2026-11-28T09:00:00+05:30" }
```

Validates:
- `scheduled_at` is at least 5 min ahead and at most 365 days ahead.
- The checklist passes **now** (so you find out today, not at 9 AM).
- The post is not currently published.

Then sets `status = 'scheduled'`, `scheduled_at` and `schedule_error = null`, and writes `blog_scheduled`. Calling it again with a new time reschedules it (same activity, metadata `{previous: …}`).

**Response 200** — `PostDetail` with `status: "scheduled"`, `status_label: "Scheduled · 28 Nov, 9:00 AM"`.

| Status | error | When |
| --- | --- | --- |
| 422 | `SCHEDULE_TOO_SOON` | Less than 5 min ahead, or in the past. `detail.earliest` = now + 5 min. |
| 422 | `SCHEDULE_TOO_FAR` | More than 365 days ahead. |
| 422 | `NAIVE_DATETIME` | No timezone offset. |
| 422 | `CHECKLIST_FAILED` | `detail.checklist`. |
| 409 | `ALREADY_PUBLISHED` | Live posts publish edits with **Update**. Scheduled updates to live posts are out of scope for v1 (Plan §11). |
| 409 | `VERSION_CONFLICT`, `POST_ARCHIVED` | — |

#### 10 · `DELETE /admin/blogs/{post_id}/schedule` — Unschedule

**Request:** `?version=22`.
**Response 200** — `PostDetail` with `status: "draft"`, `scheduled_at: null`. Writes `blog_unscheduled`.

Errors: **409 `NOT_SCHEDULED`** (also returned if the scheduler published it a second earlier — the UI reloads), 409 `VERSION_CONFLICT`.

#### 11 · `POST /admin/blogs/{post_id}/unpublish`

**Request:** `{ "version": 30 }`
Sets `status = 'draft'` and `published_revision_id = null`. Keeps `published_at`, revisions and redirects. The public URL starts returning **404** and the post drops out of the sitemap and RSS. Writes `blog_unpublished`.

**Response 200** — `PostDetail`. Errors: **409 `NOT_PUBLISHED`**, 409 `VERSION_CONFLICT`.

#### 12 · `POST /admin/blogs/{post_id}/discard-changes`

**Request:** `{ "version": 31 }`
Replaces the working copy with the live revision's snapshot. Before that, it saves the current working copy as a `restore` revision labelled "Before discard", so nothing is lost. Writes `blog_changes_discarded`.

**Response 200** — `PostDetail` with `has_unpublished_changes: false`.
Errors: **409 `NOT_PUBLISHED`**, **409 `NO_CHANGES`**, 409 `VERSION_CONFLICT`.

---

### 5.4 Preview

#### 13 · `GET /admin/blogs/{post_id}/preview?source=working|live`

Works like the project preview page (`/admin/projects/:id/preview`): the editor's **⌕ Preview** first flushes the autosave queue, then opens `/admin/blogs/{id}/preview` in a new tab. That page calls this endpoint and renders the result in the **public post template**. It has a desktop/mobile toggle, a Google result preview, a social card preview (OG), the checklist, and a Publish button that calls endpoint 8.

- `source=working` (default) renders the current working copy.
- `source=live` renders what readers see now. It is only valid while the post is published; the preview page shows a "Live / With your changes" toggle when `has_unpublished_changes` is true.

**Response 200**
```json
{
  "source": "working",
  "post_id": "…", "version": 22, "status": "draft",
  "post": PublicPostPayload,
  "search_preview": { "url_display": "uditnarayana.dev › blog › building-jerry-style-rag",
                      "title": "Building Jerry: a study in style RAG · Udit N.",
                      "description": "A frontier LLM wrapped in voice profile + style RAG…",
                      "title_truncated": false, "description_truncated": false },
  "social_preview": { "image_url": "…", "title": "…", "description": "…", "domain": "uditnarayana.dev",
                      "image_source": "og" },
  "checklist": Checklist,
  "generated_at": "2026-11-03T09:20:00Z"
}
```

`image_source` ∈ `og | cover | default`.

Errors: 404, 403; **409 `NOT_PUBLISHED`** for `source=live` on an unpublished post. Responses carry `Cache-Control: no-store`, and the preview page sets `<meta name="robots" content="noindex">`.

---

### 5.5 Revisions

Autosave **does not** create revisions; it overwrites the working copy. Revisions are made by **Save draft** (manual), Publish/Update (publish), and before a restore or discard (restore). Publish revisions are kept forever. Manual and restore revisions keep the newest 50 per post (older ones are pruned on insert).

#### 14 · `POST /admin/blogs/{post_id}/revisions` — Save draft / ⌘S

**Request**
```json
{ "version": 18, "label": "Before rewriting the intro" }
```
`label` is optional, ≤ 60 chars, and defaults to `"Saved draft"`.

**Response 201** — `RevisionSummary` (`kind: "manual"`).
**Response 200** — the latest revision, unchanged, when its `content_hash` equals the working copy's (no duplicate snapshots). The toast still says "Draft saved".

Errors: 409 `VERSION_CONFLICT` (the client PATCHes first, then sends the new version).

#### 15 · `GET /admin/blogs/{post_id}/revisions?page=1&limit=20&kind=`

**Response 200**
```json
{ "items": [RevisionSummary], "total": 7, "page": 1, "limit": 20, "total_pages": 1 }
```
Newest first. `is_live: true` marks the one behind `published_revision_id`.

#### 16 · `GET /admin/blogs/{post_id}/revisions/{revision_id}`

**Response 200** — `RevisionSummary` plus `snapshot` (all `PostWritable` fields, with `cover`/`og_image`/`category` expanded) and `content_html`. The drawer shows it read-only.

Errors: **404 `REVISION_NOT_FOUND`** (also when the revision belongs to another post).

#### 17 · `POST /admin/blogs/{post_id}/revisions/{revision_id}/restore`

**Request:** `{ "version": 25 }`
Saves the current working copy as a `restore` revision ("Before restore"), then copies the chosen snapshot into the working copy. It **does not** change the live page; you press Update for that. Writes `blog_revision_restored`.

Assets referenced by the snapshot that no longer exist are kept in the content but fail the `media_exists` checklist item. The response's `checklist` points to them.

**Response 200** — `PostDetail`. Errors: 404, 409 `VERSION_CONFLICT`, 409 `POST_ARCHIVED`.

---

### 5.6 Taxonomy

#### 18 · `GET /admin/blog-categories`

**Response 200**
```json
{ "items": [ { "id": "…", "name": "AI & Agents", "slug": "ai-agents", "description": null,
               "sort_order": 1, "post_count": 3, "published_count": 2 } ] }
```
Ordered by `sort_order`, then `name`. Seeded with AI & Agents, Web Dev, Tutorials, Opinion, Career (Plan §5).

#### 19 · `POST /admin/blog-categories`

Lets you add a category from the editor's select without leaving the page.

**Request**
```json
{ "name": "Systems Design", "description": null }
```
Name is 2–40 chars and unique case-insensitively. The slug is derived from the name and is unique. `sort_order` = max + 1.

**Response 201** — the category object. Writes no activity.

| Status | error | When |
| --- | --- | --- |
| 409 | `CATEGORY_EXISTS` | Same name (case-insensitive) or same slug. `detail.existing` = the existing category, so the select can just pick it. |
| 422 | `VALIDATION_ERROR` | — |

Rename, reorder and delete belong to Blog Manager: `PATCH /admin/blog-categories/{id}`, `PATCH /admin/blog-categories/reorder`, and `DELETE /admin/blog-categories/{id}` (409 `CATEGORY_IN_USE` while posts use it). They are listed here so nothing is missed, but are built with Blog Manager.

#### 20 · `GET /admin/blog-tags?q=lang&limit=10`

**Response 200**
```json
{ "items": [ { "tag": "langgraph", "count": 4 }, { "tag": "langchain", "count": 1 } ] }
```
Prefix match on the normalized `q`, most used first, from `unnest(tags)` across all non-archived posts. With `q` empty, it returns the most used tags. `limit` is clamped to 50.

New tags need no endpoint. Typing a new tag and pressing Enter or comma adds it to `tags` on the next PATCH.

---

### 5.7 Content helpers

#### 21 · `POST /admin/blogs/embeds/resolve`

Turns a pasted URL into a safe embed. YouTube and uploaded videos do **not** use this endpoint; they go through the media library (§6) so they appear in Media Manager and in "Used in".

**Request**
```json
{ "url": "https://codepen.io/udit/pen/abcXYZ" }
```

**Response 200**
```json
{ "provider": "codepen", "original_url": "https://codepen.io/udit/pen/abcXYZ",
  "embed_url": "https://codepen.io/udit/embed/abcXYZ?default-tab=result",
  "title": "Ink wobble filter", "thumbnail_url": null, "height": 420 }
```

| Status | error | When |
| --- | --- | --- |
| 422 | `INVALID_URL` | Not http(s), or doesn't parse. |
| 422 | `UNSUPPORTED_PROVIDER` | Host not in `embed_providers`. `detail.allowed`. If the URL is a YouTube link, `detail.hint = "Use the Video block"`. |
| 502 | `PROVIDER_UNAVAILABLE` | oEmbed lookup timed out (3 s). The client may still insert the embed with the derived `embed_url` and no title. |

The server builds `embed_url` from known URL patterns. It never accepts a client-supplied iframe `src`, and uses the existing `safe_url_fetcher` (SSRF guards) for oEmbed calls.

#### 22 · `GET /admin/blogs/link-targets?q=jerry&limit=8`

Search your own content from the link popover, so internal links are easy (good for SEO and for readers).

**Response 200**
```json
{ "items": [
  { "type": "blog", "id": "…", "title": "Building Jerry: a study in style RAG", "status": "published",
    "url": "/blog/building-jerry-style-rag" },
  { "type": "project", "id": "…", "title": "Crucible AI", "status": "published", "url": "/projects/crucible-ai" },
  { "type": "heading", "id": "the-trade-offs-no-one-talks-about", "title": "The trade-offs no one talks about",
    "url": "#the-trade-offs-no-one-talks-about" }
] }
```

- `q` matches titles (trigram, `pg_trgm` is installed).
- Optional `post_id` adds this post's own headings as `#anchor` targets.
- Drafts are returned with `status: "draft"`, and linking to one produces the `LINK_TO_DRAFT` save warning.

---

### 5.8 Scheduler

#### 23 · `POST /internal/blogs/publish-due`

Publishes every post whose time has come. It is called every minute by:
- the in-process scheduler (APScheduler, started in `app/main.py`), and
- an external cron (Supabase `pg_cron` + `pg_net`, or any cron service) as a safety net, because a sleeping host never fires an in-process timer (Plan §7).

Running it twice is harmless.

**Auth:** header `X-Cron-Secret: <BLOG_CRON_SECRET>`, compared in constant time. No user JWT. Wrong or missing secret: **401**. Not exposed in the OpenAPI docs.

**Request:** empty body.

**What it does:**
```sql
SELECT id FROM blog_posts
WHERE status = 'scheduled' AND scheduled_at <= now()
ORDER BY scheduled_at
LIMIT 20
FOR UPDATE SKIP LOCKED;
```
For each row it runs the same publish service as endpoint 8, with `published_at = scheduled_at` (the date readers see is the one you chose, even if the job ran late). Then:
- **Checklist passes** → published; activity `blog_published` with `metadata.trigger = "schedule"` and `metadata.delay_seconds`.
- **Checklist fails** (e.g. an image was deleted from Media Manager after scheduling) → `status = 'draft'`, `schedule_error` = the first failing blocker's message; activity `blog_schedule_failed`. The editor shows a red banner on next open, and the Dashboard activity feed shows it.

**Response 200**
```json
{ "checked_at": "2026-11-28T03:30:04Z",
  "published": [ { "id": "…", "slug": "building-jerry-style-rag", "delay_seconds": 4 } ],
  "failed": [ { "id": "…", "reason": "MEDIA_NOT_FOUND", "message": "Cover image no longer exists." } ] }
```

---

## 6. Reused media endpoints (already built — no new endpoints)

The editor's media picker is a modal with two tabs, **Upload from device** and **Cloudinary library**. It calls the existing media API with the folder from `editor-config.media_folders`.

| Editor action | Call | Notes |
| --- | --- | --- |
| Cover: upload from device | `POST /admin/media/upload` multipart `file`, `folder=blog/covers`, `alt_text` | 201 new / 200 duplicate (same SHA-256 → same asset, no second upload). Then `PATCH /admin/blogs/{id}` `{cover_asset_id}`. |
| Cover: pick from library | `GET /admin/media?folder=blog/covers&resource_type=image&search=&page=` (folder filter can be cleared to browse everything) | Then PATCH `cover_asset_id`. |
| Inline image / gallery images | same, `folder=blog/inline` | The client inserts nodes with `asset_id`, `public_id`, `src`, `alt`, `width`, `height` from the asset. |
| Video: upload | `POST /admin/media/upload` `folder=blog/videos`, `resource_type=video` | **Requires adding `blog/videos` to `ALLOWED_FOLDERS`** (Plan §6.3). 200 MB limit already enforced. |
| Video: pick uploaded | `GET /admin/media?resource_type=video` | — |
| Video: YouTube | `POST /admin/media/import-url` `{url: "https://youtu.be/…", folder: "blog/videos"}` | Already registers YouTube links (`source_type=youtube`, title, thumbnail, duration). Duplicate link → 200 with the existing asset. |
| OG image | upload or pick with `folder=system/og-images` | The existing upload already warns when it's not 1200×630. |
| Edit alt text of an inserted image | `PATCH /admin/media/{asset_id}` `{alt_text}` | Updates the library. The node's own `alt` is also updated in the editor; per-post alt can differ from the library default. |
| Before deleting an asset (Media Manager) | `GET /admin/media/{asset_id}/usage` | Already detects blog cover, OG and content by `public_id`. Extended to published revisions so a live page can't lose its images. |

Upload edge cases are already handled by the media endpoints: `EMPTY_FILE`, `UNSUPPORTED_FILE_TYPE` (415), `FILE_TOO_LARGE` (413), `CLOUDINARY_UPLOAD_FAILED` (502, after 3 retries), duplicates (200). The editor adds two checks of its own: covers narrower than 1200 px get a warning, and alt text is required before an image counts toward the checklist.

---

## 7. Status state machine

| From | Action | Endpoint | To |
| --- | --- | --- | --- |
| — | first autosave with title or text | 2 | `draft` |
| `draft` | Publish | 8 | `published` |
| `draft` | Schedule | 9 | `scheduled` |
| `draft` | Delete (never published) | 5 | — |
| `scheduled` | Reschedule | 9 | `scheduled` |
| `scheduled` | Unschedule | 10 | `draft` |
| `scheduled` | Publish now | 8 | `published` |
| `scheduled` | time reached, checklist passes | 23 | `published` |
| `scheduled` | time reached, checklist fails | 23 | `draft` + `schedule_error` |
| `published` | edit (autosave) | 4 | `published`, `has_unpublished_changes = true` |
| `published` + changes | Update | 8 | `published` |
| `published` + changes | Discard changes | 12 | `published` |
| `published` | Unpublish | 11 | `draft` (keeps `published_at`) |
| any but archived | Archive (Blog Manager, later) | — | `archived` |

Invariants, enforced by DB check constraints (Plan §5):
- `status = 'scheduled'` ⇔ `scheduled_at IS NOT NULL`
- `status = 'published'` ⇒ `published_revision_id IS NOT NULL`

---

## 8. Error code catalogue

| HTTP | error | Endpoints |
| --- | --- | --- |
| 400 | `MISSING_PARAM` | 6 |
| 401 | (FastAPI "Not authenticated" / "Invalid token") | all admin; 23 with bad secret |
| 403 | `FORBIDDEN` | 3–17 (not the author), all admin (not admin) |
| 404 | `POST_NOT_FOUND` | 3–17 |
| 404 | `REVISION_NOT_FOUND` | 16, 17 |
| 409 | `VERSION_CONFLICT` | 4, 5, 8–12, 14, 17 |
| 409 | `SLUG_TAKEN` | 4 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 2 |
| 409 | `NO_CHANGES` | 8, 12 |
| 409 | `ALREADY_PUBLISHED` | 9 |
| 409 | `NOT_SCHEDULED` | 10 |
| 409 | `NOT_PUBLISHED` | 11, 12, 13 (`source=live`) |
| 409 | `POST_WAS_PUBLISHED`, `POST_SCHEDULED` | 5 |
| 409 | `POST_ARCHIVED` | 4, 8, 9, 17 |
| 409 | `CATEGORY_EXISTS` | 19 |
| 413 | `CONTENT_TOO_LARGE` | 2, 4 |
| 422 | `EMPTY_POST` | 2 |
| 422 | `INVALID_CONTENT`, `INVALID_LINK`, `CONTENT_LIMIT_EXCEEDED` | 2, 4 |
| 422 | `VALIDATION_ERROR` | 2, 4, 19 |
| 422 | `RESERVED_SLUG` | 4 |
| 422 | `CATEGORY_NOT_FOUND`, `MEDIA_NOT_FOUND`, `MEDIA_TYPE_MISMATCH` | 2, 4 |
| 422 | `CHECKLIST_FAILED` | 8, 9 |
| 422 | `SCHEDULE_TOO_SOON`, `SCHEDULE_TOO_FAR`, `NAIVE_DATETIME` | 9 |
| 422 | `INVALID_URL`, `UNSUPPORTED_PROVIDER` | 21 |
| 429 | `RATE_LIMITED` | all |
| 502 | `PROVIDER_UNAVAILABLE` | 21 |

---

## 9. Edge case matrix

### A. Saving and concurrency

| # | Case | Behaviour |
| --- | --- | --- |
| A1 | Same post open in two tabs | Second tab's PATCH gets 409 `VERSION_CONFLICT`. Banner: "Edited in another tab — Reload / Keep mine". Never silently overwrites. |
| A2 | Two autosaves fire before the first create returns | Client sends one request at a time and queues the rest. `Idempotency-Key` on create covers a retried request. |
| A3 | Network drops mid-typing | Indicator "Offline — retrying". Backoff 2 s, 4 s, 8 s, then every 30 s. Unsaved doc mirrored to `localStorage` (`blog-draft:{id}` with `version`). On next load, if local is newer than `updated_at`, offer "Recover unsaved changes". |
| A4 | Token expires while writing | 401 → refresh session via Supabase client → retry once. Content stays in memory and in `localStorage`; nothing is lost. |
| A5 | Closing the tab during a save | `beforeunload` prompt if a save is in flight. Final flush with `fetch(…, {keepalive: true})` (works with an `Authorization` header, unlike `sendBeacon`). |
| A6 | Paste from Word / Google Docs / a web page | Editor paste rules map to allowlisted nodes and drop the rest (fonts, colours, scripts, iframes). Server re-validates anyway. |
| A7 | Very long post | 1 MB / 5,000-node caps. 413 shows "This post is too large — split it into a series". |
| A8 | Autosave of an archived post | 409 `POST_ARCHIVED`; editor opens read-only. |
| A9 | Saving with an older schema version after a deploy | Server upgrades the document; client reloads config when `content_schema_version` in a response is newer than its own. |

### B. Slug and URLs

| # | Case | Behaviour |
| --- | --- | --- |
| B1 | Title with emojis or non-Latin script only | Transliterate (`python-slugify`); if empty, `untitled-<6 chars>`. |
| B2 | Two drafts with the same title | Second gets `-2`, `-3`… (`slug_adjusted: true`). |
| B3 | Reserved word (`new`, `admin`, `rss`…) | 422 `RESERVED_SLUG`; slug-check shows the reason. |
| B4 | Title changed after first publish | Auto-slug stops following the title once a post has been published, even if `slug_locked` is false, so live URLs don't change by accident. |
| B5 | Slug edited on a published post | Allowed. On Update, old slug → `blog_slug_redirects` (public route answers 301). The old slug can't be taken by another post while it redirects (`redirect_reserved`). |
| B6 | Changing slug back to an old one | Its redirect row is deleted in the same transaction. |
| B7 | Canonical URL set to another post on this site | Allowed with warning; for cross-posts the canonical usually points **to** this site from Medium/dev.to (Plan §3.17). |

### C. Content blocks

| # | Case | Behaviour |
| --- | --- | --- |
| C1 | Enter on an empty list item | Leaves the list (standard). Shift+Enter inside an item adds a line in the same item; Enter on a non-empty item adds the next number. |
| C2 | Deleting numbered item 2 of 3 | Numbers recompute (1, 2). Nothing is stored, so nothing goes stale. |
| C3 | Numbered heading with no siblings | Renders "1." — editor shows a hint "only one numbered heading here". |
| C4 | Table: delete the last row or column | Deletes the whole table (with undo). |
| C5 | Table: merged cells then delete a column through the merge | colspan decremented; server re-checks rectangularity. |
| C6 | Table wider than mobile screen | Wrapped in a horizontal scroll container; header column can be sticky (`header_col`). |
| C7 | Gallery with 1 image | Editor converts it to a single `image` node; server rejects `imageGallery` with < 2 items. |
| C8 | Gallery with mixed sizes | Fixed row height (`sm/md/lg`), width from aspect ratio; scroll-snap per image. |
| C9 | YouTube video made private or deleted | The click-to-load player shows YouTube's own error; the "Watch on YouTube" link still works. The checklist can't detect this (no API call at publish). |
| C10 | Uploaded video still processing at Cloudinary | Poster shows; player starts when ready. Upload response already returns the final URL. |
| C11 | Code block with `</script>` or HTML | Escaped by the renderer; never executed. |
| C12 | Unknown language | Stored as `plaintext`. |
| C13 | `javascript:` link pasted | Editor refuses; server 422 `INVALID_LINK` as a backstop. |
| C14 | Link to own draft post | Saves with `LINK_TO_DRAFT` warning; checklist does not block (the target may publish first). |
| C15 | Image asset deleted in Media Manager while used | Media delete already returns 409 `MEDIA_IN_USE` unless forced; if forced, checklist blocker `media_exists` points at the node. |
| C16 | Same image used twice in a post | Fine; usage shows the post once. |
| C17 | Heading text duplicated | Heading ids de-duplicated (`intro`, `intro-2`) so TOC anchors stay unique. |
| C18 | A block type is disabled in config later | Existing posts still render (renderer keeps it); editor shows it read-only with "This block type is retired"; new inserts blocked. |

### D. Publishing and scheduling

| # | Case | Behaviour |
| --- | --- | --- |
| D1 | Publish clicked while an autosave is in flight | Client awaits the queue, then publishes with the new version. Server lock prevents mixing. |
| D2 | Schedule set, then content edited | Latest working copy publishes at the time. Popover says so. |
| D3 | Schedule set, then a blocker breaks (alt text removed) | Editor shows checklist red with "Scheduled publish will fail". At the time: back to `draft` + `schedule_error` + activity `blog_schedule_failed`. |
| D4 | Server asleep or down at the scheduled time | External cron wakes it; job catches up on everything with `scheduled_at <= now()`; `published_at` = the scheduled time. |
| D5 | Two app instances run the job | `FOR UPDATE SKIP LOCKED` → each post published once. |
| D6 | Unschedule a second after the scheduler published it | 409 `NOT_SCHEDULED`; UI reloads and shows Published. |
| D7 | Scheduling in the past or 2 min ahead | 422 `SCHEDULE_TOO_SOON`. The picker disables past times. |
| D8 | Timezone confusion | Client sends `+05:30`; naive times rejected; UI always labels "IST". |
| D9 | Re-publish after unpublish | `published_at` keeps the original date (trigger); `last_published_at` = now. |
| D10 | Publish with only warnings failing | Allowed. Confirm dialog lists the warnings ("Publish anyway"). |
| D11 | Media used only by the live revision is deleted | Usage scan includes published revisions → 409 `MEDIA_IN_USE`. |

### E. Taxonomy

| # | Case | Behaviour |
| --- | --- | --- |
| E1 | "AI & Agents" vs "ai & agents" | 409 `CATEGORY_EXISTS` with the existing one, which the select then picks. |
| E2 | Tag "LangGraph", "lang graph", "langgraph" | All normalize to `langgraph`; duplicates removed. |
| E3 | 9th tag | Chip input stops at 8; server 422 if forced. |
| E4 | Category deleted while a draft uses it | Delete is blocked (409 `CATEGORY_IN_USE`) in Blog Manager. If it happens anyway, FK `ON DELETE SET NULL` → checklist blocker. |

---

## 10. Implementation notes (as built, Nov 4, 2026)

Where the code differs from the sections above:

| Topic | As built |
| --- | --- |
| Unknown attributes | Dropped silently instead of rejected. Unknown **node or mark types** and unsafe URLs are still 422 (`INVALID_CONTENT`, `INVALID_LINK`). This keeps autosave from failing on harmless extra attributes the editor emits. |
| Gallery size | Accepts 1–20 items on save; the editor turns a 1-image gallery into a single image. |
| Video `src` | Derived on the server for YouTube (`youtube-nocookie.com/embed/{id}`); a client value is ignored. Cloudinary video `src` must be on `res.cloudinary.com`. Image `src` must be on `res.cloudinary.com` too. |
| Embeds | Resolved from URL patterns only (no oEmbed call), so `title` and `thumbnail_url` are null and `502 PROVIDER_UNAVAILABLE` never occurs. |
| Idempotency-Key | Stored in process memory for 24 h — correct for one API instance; needs a shared store if the API is scaled out. |
| Rate limiting | Not implemented in this build. |
| Scheduler | In-process daemon thread (`app/infrastructure/scheduling/interval_runner.py`, every `BLOG_SCHEDULER_INTERVAL_SECONDS`), no APScheduler dependency. Endpoint 23 returns 404 until `BLOG_CRON_SECRET` is set. |
| Media usage | YouTube assets have no `public_id`, so Media Manager's "Used in" doesn't see them in blog posts yet. |

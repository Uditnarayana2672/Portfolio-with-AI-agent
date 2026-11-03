"""Editor support use cases (application layer): editor config, embed
resolution and internal-link search."""
from __future__ import annotations

from app.application.dtos.blog import MEDIA_FOLDERS, BlogSettings
from app.domain.blog import checklist as rules
from app.domain.blog import content_schema as schema
from app.domain.blog.embeds import EMBED_PROVIDERS, ResolvedEmbed, resolve_embed
from app.domain.blog.slug import RESERVED_SLUGS, SLUG_MAX, SLUG_MIN
from app.domain.entities.blog_post import LinkTarget
from app.domain.repositories.blog_post_repository import BlogPostRepository
from app.application.use_cases.blog import post_workflow as wf


# The block registry the toolbar and slash menu are built from. ``enabled:
# false`` hides a block from both without a deploy of the editor.
BLOCKS: list[dict] = [
    {"type": "paragraph", "label": "Text", "icon": "¶", "group": "text",
     "slash_keywords": ["text", "paragraph", "p"], "toolbar": False, "enabled": True},
    {"type": "heading", "label": "Heading", "icon": "H", "group": "text",
     "variants": [
         {"key": "h2", "label": "Section heading", "attrs": {"level": 2}, "shortcut": "## "},
         {"key": "h3", "label": "Sub-heading", "attrs": {"level": 3}, "shortcut": "### "},
         {"key": "h3n", "label": "Numbered sub-heading", "attrs": {"level": 3, "numbered": True}, "shortcut": "#. "},
         {"key": "h4", "label": "Small heading", "attrs": {"level": 4}, "shortcut": "#### "},
     ],
     "slash_keywords": ["h2", "h3", "heading", "title", "section", "numbered"], "toolbar": True, "enabled": True},
    {"type": "bulletList", "label": "Bulleted list", "icon": "•", "group": "lists",
     "slash_keywords": ["bullet", "list", "ul"], "toolbar": True, "enabled": True},
    {"type": "orderedList", "label": "Numbered list", "icon": "1.", "group": "lists",
     "slash_keywords": ["number", "ordered", "ol", "steps"], "toolbar": True, "enabled": True},
    {"type": "blockquote", "label": "Quote", "icon": "❝", "group": "text",
     "slash_keywords": ["quote", "testimonial", "cite"], "toolbar": True, "enabled": True},
    {"type": "callout", "label": "Callout", "icon": "⚑", "group": "text",
     "variants": [{"key": v, "label": label, "icon": icon} for v, label, icon in schema.CALLOUT_VARIANTS],
     "slash_keywords": ["callout", "note", "box", "yellow", "tip", "warning"], "toolbar": True, "enabled": True},
    {"type": "codeBlock", "label": "Code block", "icon": "{ }", "group": "code",
     "slash_keywords": ["code", "snippet", "pre"], "toolbar": True, "enabled": True},
    {"type": "table", "label": "Table", "icon": "▦", "group": "code",
     "slash_keywords": ["table", "grid", "rows"], "toolbar": True, "enabled": True},
    {"type": "image", "label": "Image", "icon": "🖼", "group": "media",
     "slash_keywords": ["image", "photo", "picture"], "toolbar": True, "enabled": True},
    {"type": "imageGallery", "label": "Gallery", "icon": "▤", "group": "media",
     "slash_keywords": ["gallery", "carousel", "images", "slider"], "toolbar": True, "enabled": True},
    {"type": "video", "label": "Video", "icon": "▶", "group": "media",
     "slash_keywords": ["video", "youtube", "movie"], "toolbar": True, "enabled": True},
    {"type": "embed", "label": "Embed", "icon": "⎘", "group": "media",
     "slash_keywords": ["embed", "codepen", "figma", "gist", "loom", "sandbox"], "toolbar": True, "enabled": True},
    {"type": "horizontalRule", "label": "Divider", "icon": "—", "group": "text",
     "slash_keywords": ["divider", "hr", "line", "separator"], "toolbar": True, "enabled": True},
]


class GetEditorConfig:
    def __init__(self, settings: BlogSettings) -> None:
        self._settings = settings

    def execute(self) -> dict:
        s = self._settings
        return {
            "site_url": s.site_url,
            "blog_base_path": s.blog_base_path,
            "timezone": s.timezone,
            "title_suffix": s.title_suffix,
            "content_schema_version": schema.SCHEMA_VERSION,
            "limits": {
                "title": list(rules.TITLE_RANGE),
                "title_hard_max": wf.TITLE_MAX,
                "subtitle_max": wf.SUBTITLE_MAX,
                "excerpt": [rules.EXCERPT_IDEAL_MIN, rules.EXCERPT_MAX],
                "excerpt_hard_max": wf.EXCERPT_HARD_MAX,
                "meta_title": list(rules.META_TITLE_RANGE),
                "meta_title_hard_max": wf.META_TITLE_MAX,
                "meta_description": list(rules.META_DESCRIPTION_RANGE),
                "meta_description_hard_max": wf.META_DESCRIPTION_MAX,
                "tags_max": wf.TAGS_MAX,
                "tag_length": list(wf.TAG_LEN),
                "min_words": rules.MIN_WORDS,
                "slug_length": [SLUG_MIN, SLUG_MAX],
                "schedule_min_lead_minutes": s.schedule_min_lead_minutes,
                "schedule_max_days_ahead": s.schedule_max_days_ahead,
                "content_max_bytes": schema.MAX_CONTENT_BYTES,
                "table_max_rows": schema.TABLE_MAX_ROWS,
                "table_max_cols": schema.TABLE_MAX_COLS,
                "gallery_items": [2, schema.GALLERY_MAX_ITEMS],
                "code_max_chars": schema.MAX_TEXT_CHARS,
            },
            "blocks": BLOCKS,
            "marks": sorted(schema.MARK_SPECS),
            "palette": [{"token": t, "label": label, "bg": bg, "fg": fg} for t, label, bg, fg in schema.PALETTE],
            "callout_variants": [{"id": v, "label": label, "icon": icon} for v, label, icon in schema.CALLOUT_VARIANTS],
            "code_languages": [{"id": i, "label": label} for i, label in schema.CODE_LANGUAGES],
            "embed_providers": [{"id": p.id, "label": p.label, "hosts": list(p.hosts)} for p in EMBED_PROVIDERS],
            "media_folders": MEDIA_FOLDERS,
            "upload": {
                "image_formats": ["jpg", "jpeg", "png", "webp", "gif", "avif"],
                "image_max_bytes": 10 * 1024 * 1024,
                "video_formats": ["mp4", "webm", "mov"],
                "video_max_bytes": 200 * 1024 * 1024,
                "cover_min_width": 1200,
                "og_recommended": [1200, 630],
            },
            "reserved_slugs": sorted(RESERVED_SLUGS),
        }


class ResolveEmbed:
    def execute(self, url: str) -> ResolvedEmbed:
        return resolve_embed(url)


class SearchLinkTargets:
    def __init__(self, repo: BlogPostRepository) -> None:
        self._repo = repo

    def execute(self, query: str, limit: int) -> list[LinkTarget]:
        query = (query or "").strip()
        return self._repo.search_link_targets(query, max(1, min(limit, 20)))

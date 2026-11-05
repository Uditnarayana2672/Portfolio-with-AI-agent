"""GetBlogPreview use case (application layer).

Builds exactly what a reader will see — rendered HTML, table of contents, and
every head tag (meta, OpenGraph, Twitter, JSON-LD) — from either the working
copy or the live revision. The future public blog endpoint returns the same
``PublicPost`` shape, so preview and production can't drift.
"""
from __future__ import annotations

import dataclasses
import uuid

from app.application.dtos.blog import PreviewView, PublicPost
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow, media_url
from app.domain.blog.content_schema import normalize_document
from app.domain.entities.blog_post import BlogPost
from app.domain.exceptions import BlogRuleError, InvalidStateError

COVER_WIDTHS = (640, 1280, 1920)
GOOGLE_TITLE_MAX = 60
GOOGLE_DESCRIPTION_MAX = 158


class GetBlogPreview:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, source: str) -> PreviewView:
        wf = self._wf
        if source not in ("working", "live"):
            raise BlogRuleError("VALIDATION_ERROR", "source must be 'working' or 'live'.")
        post = wf.load(post_id, actor_id)
        shown = post
        if source == "live":
            if post.status != "published" or post.published_revision_id is None:
                raise InvalidStateError("NOT_PUBLISHED", "This post has no live version yet.")
            live = wf.repo.get_revision(post.id, post.published_revision_id)
            cols = wf.columns_from_snapshot(live.snapshot)
            shown = dataclasses.replace(post, **{k: v for k, v in cols.items() if hasattr(post, k)})

        public = self._public_post(shown)
        seo = wf.seo_effective(shown)
        domain = wf.settings.site_url.split("://", 1)[-1].rstrip("/")
        return PreviewView(
            source=source,
            post_id=post.id,
            version=post.version,
            status="draft" if post.status == "review" else post.status,
            post=public,
            search_preview={
                "url_display": f"{domain} › blog › {shown.slug}",
                "title": seo.meta_title,
                "description": seo.meta_description,
                "title_truncated": len(seo.meta_title) > GOOGLE_TITLE_MAX,
                "description_truncated": len(seo.meta_description) > GOOGLE_DESCRIPTION_MAX,
            },
            social_preview={
                "image_url": seo.og_image_url,
                "title": seo.meta_title,
                "description": seo.meta_description,
                "domain": domain,
                "image_source": "og" if shown.og_asset_id else ("cover" if shown.cover_asset_id else "default"),
            },
            checklist=wf.checklist(post),
            generated_at=wf.clock(),
        )

    def public_post(self, post: BlogPost) -> PublicPost:
        """The reader payload for one post state (used by the public blog API)."""
        return self._public_post(post)

    def _public_post(self, post: BlogPost) -> PublicPost:
        wf = self._wf
        content, _ = normalize_document(post.content or None)
        rendered = wf.renderer.render(content, link_resolver=self._resolve_link)
        settings = wf.settings
        url = settings.public_url(post.slug)
        seo = wf.seo_effective(post)

        cover = None
        if post.cover_asset_id:
            media = wf.repo.get_media([post.cover_asset_id]).get(post.cover_asset_id)
            if media and media.url:
                cover = {
                    "url": media_url(media, "f_auto,q_auto,w_1600"),
                    "alt": media.alt_text or "",
                    "width": media.width,
                    "height": media.height,
                    "srcset": ", ".join(
                        f"{media_url(media, f'f_auto,q_auto,w_{w}')} {w}w" for w in COVER_WIDTHS
                    ),
                }
        category = wf.categories.get(post.category_id) if post.category_id else None
        category_view = (
            {"name": category.name, "slug": category.slug,
             "url": f"{settings.blog_base_path}/category/{category.slug}"}
            if category else None
        )
        author = wf.repo.get_author(post.author_id)
        author_name = author.name if author and author.name else settings.author_display_name

        meta = [
            {"name": "description", "content": seo.meta_description},
            {"property": "og:type", "content": "article"},
            {"property": "og:title", "content": seo.meta_title},
            {"property": "og:description", "content": seo.meta_description},
            {"property": "og:url", "content": seo.canonical_url},
            {"name": "twitter:card", "content": "summary_large_image"},
            {"name": "twitter:title", "content": seo.meta_title},
            {"name": "twitter:description", "content": seo.meta_description},
        ]
        if seo.og_image_url:
            meta += [{"property": "og:image", "content": seo.og_image_url},
                     {"name": "twitter:image", "content": seo.og_image_url}]
        if post.published_at:
            meta.append({"property": "article:published_time", "content": post.published_at.isoformat()})
        if category:
            meta.append({"property": "article:section", "content": category.name})
        meta += [{"property": "article:tag", "content": t} for t in post.tags]

        json_ld = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": post.title,
            "description": seo.meta_description,
            "image": [seo.og_image_url] if seo.og_image_url else [],
            "datePublished": post.published_at.isoformat() if post.published_at else None,
            "dateModified": post.updated_at.isoformat(),
            "author": {"@type": "Person", "name": author_name},
            "articleSection": category.name if category else None,
            "keywords": ", ".join(post.tags),
            "wordCount": rendered.word_count,
            "mainEntityOfPage": seo.canonical_url,
        }
        return PublicPost(
            title=post.title,
            subtitle=post.subtitle,
            slug=post.slug,
            url=url,
            cover=cover,
            category=category_view,
            tags=[{"name": t, "url": f"{settings.blog_base_path}/tag/{t}"} for t in post.tags],
            author={"name": author_name, "avatar_url": author.avatar_url if author else None},
            published_at=post.published_at,
            updated_at=post.updated_at,
            reading_time_min=wf.reading_time(rendered.word_count),
            word_count=rendered.word_count,
            toc=rendered.toc,
            content_html=rendered.html,
            head={
                "title": seo.meta_title,
                "meta": meta,
                "links": [{"rel": "canonical", "href": seo.canonical_url}],
                "json_ld": json_ld,
            },
        )

    def _resolve_link(self, ref: dict) -> str | None:
        target = self._wf.repo.link_target_status(ref["type"], uuid.UUID(ref["id"]))
        if not target:
            return None
        # The blog and the portfolio are separate sites, so links are absolute.
        settings = self._wf.settings
        base = settings.portfolio_url if ref["type"] == "project" else settings.site_url
        return f"{base.rstrip('/')}{target[1]}"

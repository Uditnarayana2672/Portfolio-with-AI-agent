"""Public blog reads (application layer).

Every read uses the live revision, so saved-but-unpublished edits never appear.
"""
from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass

from app.application.dtos.blog import PublicPost
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow, media_url
from app.application.use_cases.blog.preview import GetBlogPreview
from app.domain.entities.blog_post import BlogPost
from app.domain.exceptions import NotFoundError
from app.domain.repositories.public_site_repository import PublicSiteRepository

CARD_IMAGE = "f_auto,q_auto,w_960"


@dataclass(frozen=True)
class BlogCard:
    title: str
    subtitle: str | None
    slug: str
    url: str
    excerpt: str | None
    cover: dict | None
    category: dict | None
    tags: list[dict]
    reading_time_min: int
    published_at: object


@dataclass(frozen=True)
class MovedPost(Exception):
    slug: str


class PublicBlog:
    def __init__(self, repo: PublicSiteRepository, workflow: BlogPostWorkflow) -> None:
        self._repo = repo
        self._wf = workflow

    # ── live state ───────────────────────────────────────────────────────

    def _live_posts(self) -> list[BlogPost]:
        posts = []
        for post, snapshot in self._repo.live_blog_posts():
            cols = self._wf.columns_from_snapshot(snapshot)
            posts.append(dataclasses.replace(post, **{k: v for k, v in cols.items() if hasattr(post, k)}))
        return posts

    def _cards(self, posts: list[BlogPost]) -> list[BlogCard]:
        wf = self._wf
        settings = wf.settings
        media = wf.repo.get_media([p.cover_asset_id for p in posts if p.cover_asset_id])
        categories = {c[0]: c for c in self._repo.blog_categories()}
        cards = []
        for post in posts:
            cover_media = media.get(post.cover_asset_id) if post.cover_asset_id else None
            category = categories.get(post.category_id)
            cards.append(BlogCard(
                title=post.title,
                subtitle=post.subtitle,
                slug=post.slug,
                url=settings.public_url(post.slug),
                excerpt=post.excerpt,
                cover=(
                    {"url": media_url(cover_media, CARD_IMAGE), "alt": cover_media.alt_text or "",
                     "width": cover_media.width, "height": cover_media.height}
                    if cover_media and cover_media.url else None
                ),
                category=(
                    {"name": category[1], "slug": category[2],
                     "url": f"{settings.blog_base_path}/category/{category[2]}"}
                    if category else None
                ),
                tags=[{"name": t, "url": f"{settings.blog_base_path}/tag/{t}"} for t in post.tags],
                reading_time_min=wf.reading_time(post.word_count),
                published_at=post.published_at,
            ))
        return cards

    # ── reads ────────────────────────────────────────────────────────────

    def list(
        self, *, q: str | None, category: str | None, tag: str | None, exclude: str | None, limit: int, offset: int,
    ) -> tuple[list[BlogCard], int]:
        posts = self._live_posts()
        if q:
            hits = self._repo.search_blog_ids(q)
            posts = [p for p in posts if p.id in hits]
        if category:
            ids = [c[0] for c in self._repo.blog_categories() if c[2] == category]
            posts = [p for p in posts if p.category_id in ids]
        if tag:
            posts = [p for p in posts if tag.lower() in (t.lower() for t in p.tags)]
        if exclude:
            posts = [p for p in posts if p.slug != exclude]
        return self._cards(posts[offset: offset + limit]), len(posts)

    def _by_slug(self, slug: str) -> BlogPost:
        posts = self._live_posts()
        found = next((p for p in posts if p.slug == slug), None)
        if found:
            return found
        old_owner = self._repo.blog_id_by_old_slug(slug)
        moved = next((p for p in posts if p.id == old_owner), None) if old_owner else None
        if moved:
            raise MovedPost(moved.slug)
        raise NotFoundError(f"Post '{slug}' not found.")

    def get(self, slug: str) -> tuple[PublicPost, BlogPost]:
        post = self._by_slug(slug)
        return GetBlogPreview(self._wf).public_post(post), post

    def require_id(self, slug: str) -> uuid.UUID:
        try:
            return self._by_slug(slug).id
        except MovedPost as moved:
            return self._by_slug(moved.slug).id

    def comments_open(self, slug: str) -> bool:
        return self._by_slug(slug).allow_comments

    def related(self, slug: str, limit: int) -> list[BlogCard]:
        posts = self._live_posts()
        current = next((p for p in posts if p.slug == slug), None)
        if current is None:
            raise NotFoundError(f"Post '{slug}' not found.")
        others = [p for p in posts if p.id != current.id]
        tags = {t.lower() for t in current.tags}

        def score(post: BlogPost) -> tuple[int, int]:
            shared = len(tags & {t.lower() for t in post.tags})
            same_category = int(post.category_id is not None and post.category_id == current.category_id)
            return (-shared, -same_category)

        return self._cards(sorted(others, key=score)[:limit])

    def related_to_terms(self, terms: list[str], limit: int) -> list[BlogCard]:
        """Posts whose tags match a project's tech stack, then the newest."""
        wanted = {t.lower() for t in terms}
        posts = self._live_posts()
        ranked = sorted(posts, key=lambda p: -len(wanted & {t.lower() for t in p.tags}))
        return self._cards(ranked[:limit])

    def categories(self) -> list[dict]:
        posts = self._live_posts()
        return [
            {"name": name, "slug": slug, "description": description,
             "post_count": sum(1 for p in posts if p.category_id == category_id)}
            for category_id, name, slug, description in self._repo.blog_categories()
        ]

    def tags(self) -> list[dict]:
        counts: dict[str, int] = {}
        for post in self._live_posts():
            for tag in post.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return [{"tag": t, "count": n} for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    def redirects(self) -> list[dict]:
        slugs = {p.id: p.slug for p in self._live_posts()}
        base = self._wf.settings.blog_base_path
        return [
            {"from": f"{base}/{old}", "to": f"{base}/{slugs[post_id]}"}
            for old, post_id in self._repo.blog_redirects()
            if post_id in slugs and slugs[post_id] != old
        ]

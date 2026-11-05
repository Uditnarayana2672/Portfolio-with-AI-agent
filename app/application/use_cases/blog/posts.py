"""Blog post CRUD use cases (application layer).

CreateBlogPost, GetBlogPost, UpdateBlogPost (autosave), DeleteBlogPost and
CheckBlogSlug. The shared field rules live in post_workflow.
"""
from __future__ import annotations

import uuid

from app.application.dtos.blog import WRITABLE_FIELDS, PostView, SaveResult, SlugCheckResult
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.domain.blog.content_schema import empty_document
from app.domain.blog.slug import slug_issue, slugify, suggest_free
from app.domain.exceptions import BlogRuleError, InvalidStateError


def _writable(changes: dict) -> dict:
    return {k: v for k, v in changes.items() if k in WRITABLE_FIELDS}


def _has_body_text(content: dict | None) -> bool:
    stack = [content or {}]
    while stack:
        node = stack.pop()
        if node.get("type") == "text" and node.get("text", "").strip():
            return True
        if node.get("type") in ("image", "imageGallery", "video", "embed"):
            return True
        stack.extend(node.get("content", []) or [])
    return False


class CreateBlogPost:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, author_id: uuid.UUID, changes: dict) -> PostView:
        changes = _writable(changes)
        if not (changes.get("title") or "").strip() and not _has_body_text(changes.get("content")):
            raise BlogRuleError("EMPTY_POST", "Add a title or some text first.")
        changes.setdefault("content", empty_document())
        changes.setdefault("title", "")

        cols, _warnings, _adjusted = self._wf.apply_changes(changes, None)
        cols.update(author_id=author_id, status="draft", visibility="public")
        post = self._wf.repo.add(cols)
        self._wf.record("blog_created", post, author_id, f"Blog post '{post.title or post.slug}' created as draft.")
        return self._wf.view(post)


class GetBlogPost:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID) -> PostView:
        return self._wf.view(self._wf.load(post_id, actor_id))


class UpdateBlogPost:
    """Autosave: apply a partial change under the optimistic version lock.
    Never logs activity — only lifecycle actions do."""

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int, changes: dict) -> SaveResult:
        wf = self._wf
        post = wf.load(post_id, actor_id)
        wf.ensure_editable(post)
        wf.check_version(post, version)

        cols, warnings, slug_adjusted = wf.apply_changes(_writable(changes), post)
        updated = wf.repo.update(post.id, version, cols)
        return SaveResult(
            id=updated.id,
            version=updated.version,
            updated_at=updated.updated_at,
            slug=updated.slug,
            slug_adjusted=slug_adjusted,
            stats=wf.stats(updated),
            has_unpublished_changes=wf.has_unpublished_changes(updated),
            checklist=wf.checklist(updated),
            warnings=warnings,
        )


class DeleteBlogPost:
    """Hard delete — only for posts that were never live."""

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> None:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        wf.check_version(post, version)
        if post.published_at is not None or post.status == "published":
            raise InvalidStateError(
                "POST_WAS_PUBLISHED",
                "This post has been live. Unpublish and archive it instead of deleting.",
            )
        if post.status == "scheduled":
            raise InvalidStateError("POST_SCHEDULED", "Unschedule the post before deleting it.")
        wf.record("blog_deleted", post, actor_id, f"Blog post '{post.title or post.slug}' deleted.")
        wf.repo.delete(post.id)


class CheckBlogSlug:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, raw: str, exclude_id: uuid.UUID | None) -> SlugCheckResult:
        repo = self._wf.repo
        slug = slugify(raw)
        reason = slug_issue(slug)

        def taken(candidate: str) -> bool:
            owner = repo.slug_owner(candidate)
            return owner is not None and owner != exclude_id

        def redirected(candidate: str) -> bool:
            owner = repo.redirect_owner(candidate)
            return owner is not None and owner != exclude_id

        if reason is None and taken(slug):
            reason = "taken"
        elif reason is None and redirected(slug):
            reason = "redirect_reserved"

        suggested = None
        if reason in ("taken", "redirect_reserved"):
            suggested = suggest_free(slug, lambda s: taken(s) or redirected(s))
        return SlugCheckResult(input=raw, slug=slug, available=reason is None, reason=reason, suggested=suggested)

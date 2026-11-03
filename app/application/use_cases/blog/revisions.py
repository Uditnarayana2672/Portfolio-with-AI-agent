"""Blog revision use cases (application layer).

Revisions are made by Save draft (manual), Publish/Update (publish) and before
a restore or discard (restore). Autosave never creates one.
"""
from __future__ import annotations

import uuid

from app.application.dtos.blog import PostView, RevisionPage, RevisionView
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.domain.exceptions import BlogNotFoundError

DEFAULT_LABEL = "Saved draft"


class CreateBlogRevision:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(
        self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int, label: str | None
    ) -> tuple[RevisionView, bool]:
        """Returns (revision, created). An unchanged post returns the latest
        revision with ``created=False`` instead of a duplicate snapshot."""
        wf = self._wf
        post = wf.load(post_id, actor_id)
        wf.check_version(post, version)

        latest = wf.repo.latest_revision(post.id)
        if latest is not None and latest.content_hash == post.content_hash:
            return RevisionView(latest, latest.id == post.published_revision_id), False

        rev = wf.repo.add_revision(
            post_id=post.id, kind="manual", label=(label or "").strip()[:60] or DEFAULT_LABEL,
            snapshot=wf.snapshot(post), content_html=post.content_html,
            content_hash=post.content_hash or "", word_count=post.word_count, created_by=actor_id,
        )
        wf.repo.prune_revisions(post.id, wf.settings.revisions_keep, post.published_revision_id)
        return RevisionView(rev, False), True


class ListBlogRevisions:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(
        self, post_id: uuid.UUID, actor_id: uuid.UUID, *, kind: str | None, page: int, limit: int
    ) -> RevisionPage:
        post = self._wf.load(post_id, actor_id)
        limit = max(1, min(limit, 100))
        items, total = self._wf.repo.list_revisions(post.id, kind=kind, page=page, limit=limit)
        return RevisionPage(
            items=[RevisionView(r, r.id == post.published_revision_id) for r in items],
            total=total, page=page, limit=limit,
        )


class GetBlogRevision:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, revision_id: uuid.UUID, actor_id: uuid.UUID) -> RevisionView:
        post = self._wf.load(post_id, actor_id)
        rev = self._wf.repo.get_revision(post.id, revision_id)
        if rev is None:
            raise BlogNotFoundError("REVISION_NOT_FOUND", f"Revision {revision_id} not found.")
        return RevisionView(rev, rev.id == post.published_revision_id)


class RestoreBlogRevision:
    """Copy a revision into the working copy. Never touches the live page."""

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(
        self, post_id: uuid.UUID, revision_id: uuid.UUID, actor_id: uuid.UUID, version: int
    ) -> PostView:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        wf.ensure_editable(post)
        wf.check_version(post, version)
        rev = wf.repo.get_revision(post.id, revision_id)
        if rev is None:
            raise BlogNotFoundError("REVISION_NOT_FOUND", f"Revision {revision_id} not found.")

        wf.repo.add_revision(
            post_id=post.id, kind="restore", label="Before restore",
            snapshot=wf.snapshot(post), content_html=post.content_html,
            content_hash=post.content_hash or "", word_count=post.word_count, created_by=actor_id,
        )
        cols = wf.columns_from_snapshot(rev.snapshot)
        # Live URLs don't move by restoring (slug changes go through the slug
        # line), and a slug another post took since can't be reclaimed.
        if post.published_at is not None or wf.repo.slug_owner(cols["slug"]) not in (None, post.id):
            cols.pop("slug")
            cols["content_hash"] = wf.hash_state(wf.publishable_state(post, cols))
        updated = wf.repo.update(post.id, version, cols)
        wf.repo.prune_revisions(post.id, wf.settings.revisions_keep, post.published_revision_id)
        wf.record("blog_revision_restored", updated, actor_id,
                  f"Revision of '{updated.title}' restored ({rev.label or rev.kind}).",
                  {"revision_id": str(rev.id)})
        return wf.view(updated)

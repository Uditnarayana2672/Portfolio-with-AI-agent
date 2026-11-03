"""Blog publishing use cases (application layer).

Checklist, Publish/Update, Schedule, Unschedule, Unpublish, Discard changes,
and PublishDuePosts (the scheduler's run). All publishing goes through
``BlogPostWorkflow.publish`` so the button and the scheduler behave the same.
"""
from __future__ import annotations

import datetime
import uuid

from app.application.dtos.blog import DueRunResult, PostView
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.domain.blog.checklist import Checklist
from app.domain.exceptions import (
    BlogRuleError,
    ChecklistFailedError,
    InvalidStateError,
)


class GetBlogChecklist:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID) -> Checklist:
        return self._wf.checklist(self._wf.load(post_id, actor_id))


class PublishBlogPost:
    """Publish a draft/scheduled post, or Update a live one."""

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> PostView:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        wf.ensure_editable(post)
        wf.check_version(post, version)
        return wf.view(wf.publish(post, actor_id, trigger="manual"))


class ScheduleBlogPost:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(
        self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int, scheduled_at: datetime.datetime
    ) -> PostView:
        wf = self._wf
        if scheduled_at.tzinfo is None:
            raise BlogRuleError("NAIVE_DATETIME", "Send the time with a timezone offset.")
        post = wf.load(post_id, actor_id, for_update=True)
        wf.ensure_editable(post)
        wf.check_version(post, version)
        if post.status == "published":
            raise InvalidStateError("ALREADY_PUBLISHED", "This post is live — use Update to publish edits.")

        now = wf.clock()
        earliest = now + datetime.timedelta(minutes=wf.settings.schedule_min_lead_minutes)
        if scheduled_at < earliest:
            raise BlogRuleError(
                "SCHEDULE_TOO_SOON",
                f"Pick a time at least {wf.settings.schedule_min_lead_minutes} minutes from now.",
                {"earliest": earliest.isoformat()},
            )
        if scheduled_at > now + datetime.timedelta(days=wf.settings.schedule_max_days_ahead):
            raise BlogRuleError("SCHEDULE_TOO_FAR", "Pick a time within the next year.")

        checklist = wf.checklist(post)
        if not checklist.can_publish:
            raise ChecklistFailedError(checklist)

        previous = post.scheduled_at
        updated = wf.repo.update(post.id, version, {
            "status": "scheduled",
            "scheduled_at": scheduled_at.astimezone(datetime.timezone.utc),
            "schedule_error": None,
        })
        wf.record(
            "blog_scheduled", updated, actor_id,
            f"Blog post '{updated.title}' scheduled.",
            {"scheduled_at": updated.scheduled_at.isoformat(),
             "previous": previous.isoformat() if previous else None},
        )
        return wf.view(updated)


class UnscheduleBlogPost:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> PostView:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        if post.status != "scheduled":
            raise InvalidStateError("NOT_SCHEDULED", "This post is not scheduled.")
        wf.check_version(post, version)
        updated = wf.repo.update(post.id, version, {"status": "draft", "scheduled_at": None})
        wf.record("blog_unscheduled", updated, actor_id, f"Blog post '{updated.title}' unscheduled.")
        return wf.view(updated)


class UnpublishBlogPost:
    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> PostView:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        if post.status != "published":
            raise InvalidStateError("NOT_PUBLISHED", "This post is not live.")
        wf.check_version(post, version)
        updated = wf.repo.update(post.id, version, {"status": "draft", "published_revision_id": None})
        wf.record("blog_unpublished", updated, actor_id, f"Blog post '{updated.title}' unpublished.")
        return wf.view(updated)


class DiscardBlogChanges:
    """Reset the working copy to the live revision, keeping a safety copy."""

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self, post_id: uuid.UUID, actor_id: uuid.UUID, version: int) -> PostView:
        wf = self._wf
        post = wf.load(post_id, actor_id, for_update=True)
        if post.status != "published" or post.published_revision_id is None:
            raise InvalidStateError("NOT_PUBLISHED", "Only a live post has changes to discard.")
        wf.check_version(post, version)
        if not wf.has_unpublished_changes(post):
            raise InvalidStateError("NO_CHANGES", "There are no unpublished changes.")

        live = wf.repo.get_revision(post.id, post.published_revision_id)
        wf.repo.add_revision(
            post_id=post.id, kind="restore", label="Before discard",
            snapshot=wf.snapshot(post), content_html=post.content_html,
            content_hash=post.content_hash or "", word_count=post.word_count, created_by=actor_id,
        )
        updated = wf.repo.update(post.id, version, wf.columns_from_snapshot(live.snapshot))
        wf.repo.prune_revisions(post.id, wf.settings.revisions_keep, post.published_revision_id)
        wf.record("blog_changes_discarded", updated, actor_id,
                  f"Unpublished changes to '{updated.title}' discarded.")
        return wf.view(updated)


class PublishDuePosts:
    """The scheduler's run: publish every scheduled post whose time has come.

    Rows are claimed with SKIP LOCKED so overlapping runs never double-publish.
    A post whose checklist fails at fire time goes back to draft with the reason.
    """

    BATCH = 20

    def __init__(self, workflow: BlogPostWorkflow) -> None:
        self._wf = workflow

    def execute(self) -> DueRunResult:
        wf = self._wf
        published: list[dict] = []
        failed: list[dict] = []
        for post_id in wf.repo.due_scheduled_ids(self.BATCH):
            post = wf.repo.get(post_id, for_update=True)
            if post is None or post.status != "scheduled" or post.scheduled_at is None:
                continue
            delay = int((wf.clock() - post.scheduled_at).total_seconds())
            try:
                updated = wf.publish(post, None, trigger="schedule", published_at=post.scheduled_at)
            except ChecklistFailedError as exc:
                item = exc.checklist.first_failure()
                reason = item.message or item.label if item else "Checklist failed."
                wf.repo.update(post.id, None, {
                    "status": "draft", "scheduled_at": None,
                    "schedule_error": f"Scheduled publish failed: {reason}",
                })
                wf.record("blog_schedule_failed", post, None,
                          f"Scheduled publish of '{post.title}' failed: {reason}",
                          {"reason": item.key if item else None})
                failed.append({"id": str(post.id), "reason": item.key if item else None, "message": reason})
                continue
            published.append({"id": str(updated.id), "slug": updated.slug, "delay_seconds": max(delay, 0)})
        return DueRunResult(checked_at=wf.clock(), published=published, failed=failed)

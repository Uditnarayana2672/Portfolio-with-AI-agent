"""Admin inbox, moderation, subscribers and site rebuild endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import (
    get_email_sender,
    get_inbox_repository,
    get_prepare_newsletter_send,
    get_site_builds,
)
from app.api.v1.endpoints.internal_blogs import require_cron_secret
from app.api.v1.schemas.public_site import (
    AdminCommentList,
    AdminCommentResponse,
    AdminMessageList,
    AdminMessageResponse,
    AdminSubscriberList,
    CommentPatchRequest,
    CommentReplyRequest,
    FlushResponse,
    InboxCounts,
    MessagePatchRequest,
    NewsletterSendRequest,
    NewsletterSendResponse,
    SiteBuildList,
    SiteBuildRequest,
    SiteBuildResponse,
)
from app.application.interfaces.site_services import EmailSender
from app.application.use_cases.inbox.newsletter_send import (
    NewsletterAlreadySentError,
    NewsletterLimitError,
    PrepareNewsletterSend,
    deliver_newsletter,
)
from app.application.use_cases.public_site.site_builds import SiteBuilds, build_state
from app.domain.exceptions import BlogNotFoundError, InvalidStateError, VersionConflictError
from app.domain.exceptions import PermissionError as DomainPermissionError
from app.domain.repositories.inbox_repository import AdminComment, InboxRepository
from app.domain.repositories.site_build_repository import SiteBuildState
from app.infrastructure.config import settings
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin", tags=["Admin inbox"])
internal_router = APIRouter(prefix="/internal/site-builds", include_in_schema=False)

_LIST_LIMIT = Query(25, ge=1, le=100)


def _missing(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": f"{name} not found."})


def _comment(c: AdminComment) -> AdminCommentResponse:
    return AdminCommentResponse(
        id=c.id, post={"id": c.post_id, "title": c.post_title, "slug": c.post_slug},
        author_name=c.author_name, author_email=c.author_email, content=c.content, status=c.status,
        parent_id=c.parent_id, created_at=c.created_at,
    )


def _build(row: SiteBuildState) -> SiteBuildResponse:
    return SiteBuildResponse(
        site=row.site, state=build_state(row), dirty_since=row.dirty_since, last_triggered_at=row.last_triggered_at,
    )


@router.get("/inbox/counts", response_model=InboxCounts, summary="Command Deck counts")
def inbox_counts(
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> InboxCounts:
    return InboxCounts(**repo.counts())


# ── comments ─────────────────────────────────────────────────────────────────


@router.get("/comments", response_model=AdminCommentList, summary="Moderation queue")
def list_comments(
    comment_status: str = Query("pending", alias="status", pattern="^(pending|approved|all)$"),
    limit: int = _LIST_LIMIT,
    offset: int = Query(0, ge=0),
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> AdminCommentList:
    rows, total = repo.list_comments(comment_status, limit, offset)
    return AdminCommentList(items=[_comment(c) for c in rows], total=total)


@router.patch("/comments/{comment_id}", response_model=AdminCommentResponse, summary="Approve or hide")
def patch_comment(
    comment_id: uuid.UUID,
    body: CommentPatchRequest,
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> AdminCommentResponse:
    row = repo.set_comment_approved(comment_id, body.status == "approved")
    if row is None:
        raise _missing("Comment")
    return _comment(row)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Delete, with replies")
def delete_comment(
    comment_id: uuid.UUID,
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> None:
    if not repo.delete_comment(comment_id):
        raise _missing("Comment")


@router.post("/comments/{comment_id}/replies", response_model=AdminCommentResponse,
             status_code=status.HTTP_201_CREATED, summary="Reply as the author")
def reply_to_comment(
    comment_id: uuid.UUID,
    body: CommentReplyRequest,
    admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> AdminCommentResponse:
    parent = repo.get_comment(comment_id)
    if parent is None:
        raise _missing("Comment")
    # One reply level: answering a reply attaches to its top comment.
    top = parent.parent_id or parent.id
    return _comment(repo.add_author_reply(
        post_id=parent.post_id, parent_id=top, author_id=admin.id, author_name=admin.name, content=body.content,
    ))


# ── contact messages ─────────────────────────────────────────────────────────


@router.get("/contact-messages", response_model=AdminMessageList, summary="Inbox")
def list_messages(
    message_status: str = Query("all", alias="status", pattern="^(unread|read|all)$"),
    limit: int = _LIST_LIMIT,
    offset: int = Query(0, ge=0),
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> AdminMessageList:
    rows, total = repo.list_messages(message_status, limit, offset)
    return AdminMessageList(items=[AdminMessageResponse.model_validate(m) for m in rows], total=total)


@router.patch("/contact-messages/{message_id}", response_model=AdminMessageResponse, summary="Mark read or unread")
def patch_message(
    message_id: uuid.UUID,
    body: MessagePatchRequest,
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> AdminMessageResponse:
    row = repo.set_message_read(message_id, body.read)
    if row is None:
        raise _missing("Message")
    return AdminMessageResponse.model_validate(row)


@router.delete("/contact-messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Delete")
def delete_message(
    message_id: uuid.UUID,
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> None:
    if not repo.delete_message(message_id):
        raise _missing("Message")


# ── subscribers ──────────────────────────────────────────────────────────────


@router.get("/subscribers", response_model=AdminSubscriberList, summary="Subscriber list")
def list_subscribers(
    subscriber_status: str = Query("all", alias="status", pattern="^(pending|active|unsubscribed|bounced|all)$"),
    limit: int = _LIST_LIMIT,
    offset: int = Query(0, ge=0),
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> AdminSubscriberList:
    rows, total = repo.list_subscribers(subscriber_status, limit, offset)
    return AdminSubscriberList(items=rows, total=total)


@router.delete("/subscribers/{subscriber_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Remove")
def delete_subscriber(
    subscriber_id: uuid.UUID,
    _admin: Users = Depends(get_current_admin),
    repo: InboxRepository = Depends(get_inbox_repository),
) -> None:
    if not repo.delete_subscriber(subscriber_id):
        raise _missing("Subscriber")


@router.post("/blogs/{post_id}/newsletter-sends", response_model=NewsletterSendResponse,
             status_code=status.HTTP_202_ACCEPTED, summary="Email a post to subscribers")
def send_newsletter(
    post_id: uuid.UUID,
    body: NewsletterSendRequest,
    background: BackgroundTasks,
    admin: Users = Depends(get_current_admin),
    use_case: PrepareNewsletterSend = Depends(get_prepare_newsletter_send),
    email: EmailSender = Depends(get_email_sender),
) -> NewsletterSendResponse:
    def conflict(code: str, message: str) -> HTTPException:
        return HTTPException(status_code=409, detail={"error": code, "message": message})

    try:
        send = use_case.execute(post_id, admin.id, body.version)
    except BlogNotFoundError as exc:
        raise _missing("Post") from exc
    except DomainPermissionError as exc:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": str(exc)}) from exc
    except VersionConflictError as exc:
        raise conflict("VERSION_CONFLICT", "This post changed. Reload and try again.") from exc
    except InvalidStateError as exc:
        raise conflict(exc.code, str(exc)) from exc
    except NewsletterAlreadySentError as exc:
        raise conflict("ALREADY_SENT", str(exc)) from exc
    except NewsletterLimitError as exc:
        raise conflict("DAILY_LIMIT_EXCEEDED", str(exc)) from exc
    background.add_task(deliver_newsletter, send, email, settings.SITE_URL)
    return NewsletterSendResponse(recipients=len(send.recipients), post_slug=send.slug, status="sending")


# ── live site rebuilds ───────────────────────────────────────────────────────


@router.get("/site-builds", response_model=SiteBuildList, summary="Live site status")
def site_builds(
    _admin: Users = Depends(get_current_admin),
    builds: SiteBuilds = Depends(get_site_builds),
) -> SiteBuildList:
    return SiteBuildList(items=[_build(r) for r in builds.status()])


@router.post("/site-builds", response_model=SiteBuildResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Rebuild a site now")
def rebuild_site(
    body: SiteBuildRequest,
    _admin: Users = Depends(get_current_admin),
    builds: SiteBuilds = Depends(get_site_builds),
) -> SiteBuildResponse:
    return _build(builds.rebuild_now(body.site))


@internal_router.post("/flush", response_model=FlushResponse)
def flush_site_builds(
    _: None = Depends(require_cron_secret),
    builds: SiteBuilds = Depends(get_site_builds),
) -> FlushResponse:
    return FlushResponse(triggered=builds.flush())

"""Admin blog editor endpoints (presentation layer).

Thin controllers: parse the request, call the use case, translate domain errors
to HTTP, serialize the result. Contract: "New Blog Post API.md" (endpoints
1–17, 21, 22). Errors use the projects envelope:
``{"detail": {"error": CODE, "message": ..., "detail": {...}}}``.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import (
    get_blog_checklist,
    get_blog_preview,
    get_check_blog_slug,
    get_create_blog_post,
    get_create_blog_revision,
    get_delete_blog_post,
    get_discard_blog_changes,
    get_editor_config,
    get_get_blog_post,
    get_get_blog_revision,
    get_list_blog_revisions,
    get_publish_blog_post,
    get_resolve_embed,
    get_restore_blog_revision,
    get_schedule_blog_post,
    get_search_link_targets,
    get_unpublish_blog_post,
    get_unschedule_blog_post,
    get_update_blog_post,
)
from app.api.v1.schemas.blog import (
    ChecklistResponse,
    CreateRevisionRequest,
    LinkTargetListResponse,
    LinkTargetResponse,
    PostDetailResponse,
    PostWritable,
    PreviewResponse,
    ResolvedEmbedResponse,
    ResolveEmbedRequest,
    RevisionAuthor,
    RevisionDetailResponse,
    RevisionListResponse,
    RevisionSummaryResponse,
    SaveResultResponse,
    ScheduleRequest,
    SlugCheckResponse,
    UpdatePostRequest,
    VersionRequest,
)
from app.application.dtos.blog import RevisionView
from app.application.use_cases.blog.editor_support import GetEditorConfig, ResolveEmbed, SearchLinkTargets
from app.application.use_cases.blog.posts import (
    CheckBlogSlug,
    CreateBlogPost,
    DeleteBlogPost,
    GetBlogPost,
    UpdateBlogPost,
)
from app.application.use_cases.blog.preview import GetBlogPreview
from app.application.use_cases.blog.publishing import (
    DiscardBlogChanges,
    GetBlogChecklist,
    PublishBlogPost,
    ScheduleBlogPost,
    UnpublishBlogPost,
    UnscheduleBlogPost,
)
from app.application.use_cases.blog.revisions import (
    CreateBlogRevision,
    GetBlogRevision,
    ListBlogRevisions,
    RestoreBlogRevision,
)
from app.domain.exceptions import (
    BlogNotFoundError,
    BlogRuleError,
    ChecklistFailedError,
    ContentTooLargeError,
    InvalidStateError,
    NotFoundError,
    PermissionError,
    SlugTakenError,
    VersionConflictError,
)
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin/blogs", tags=["Blog editor"])


# ── error translation ────────────────────────────────────────────────────────


def _http(code: int, error: str, message: str, detail: dict | None = None) -> HTTPException:
    body: dict = {"error": error, "message": message}
    if detail:
        body["detail"] = detail
    return HTTPException(status_code=code, detail=body)


@contextmanager
def domain_errors() -> Iterator[None]:
    """Map blog domain exceptions to the API's status codes and error codes."""
    try:
        yield
    except VersionConflictError as exc:
        raise _http(409, "VERSION_CONFLICT", str(exc), {
            "current_version": exc.current_version,
            "updated_at": exc.updated_at.isoformat() if exc.updated_at else None,
        }) from exc
    except SlugTakenError as exc:
        raise _http(409, "SLUG_TAKEN", str(exc), {"suggestion": exc.suggested}) from exc
    except InvalidStateError as exc:
        raise _http(409, exc.code, str(exc), exc.detail) from exc
    except ChecklistFailedError as exc:
        checklist = ChecklistResponse.model_validate(exc.checklist).model_dump(mode="json")
        raise _http(422, "CHECKLIST_FAILED", str(exc), {"checklist": checklist}) from exc
    except ContentTooLargeError as exc:
        raise _http(413, exc.code, str(exc), exc.detail) from exc
    except BlogRuleError as exc:
        raise _http(422, exc.code, str(exc), exc.detail) from exc
    except BlogNotFoundError as exc:
        raise _http(404, exc.code, str(exc)) from exc
    except NotFoundError as exc:
        raise _http(404, "NOT_FOUND", str(exc)) from exc
    except PermissionError as exc:
        raise _http(403, "FORBIDDEN", str(exc)) from exc


def _detail(view) -> dict:
    return PostDetailResponse.model_validate(view).model_dump(mode="json")


# ── idempotent create ────────────────────────────────────────────────────────
# Process-local: enough to stop two racing autosaves from creating two drafts
# on a single API instance. (A shared store is needed if this ever scales out.)

_IDEMPOTENCY_TTL_SECONDS = 24 * 3600
_idempotency: dict[tuple[uuid.UUID, str], tuple[uuid.UUID, str, float]] = {}
_idempotency_lock = threading.Lock()


def _body_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


# ── 1. editor config ─────────────────────────────────────────────────────────


@router.get("/editor-config", summary="Editor setup: blocks, limits, palette, languages")
def editor_config(
    _admin: Users = Depends(get_current_admin),
    use_case: GetEditorConfig = Depends(get_editor_config),
) -> dict:
    return use_case.execute()


# ── 6. slug check (static routes before /{post_id}) ──────────────────────────


@router.get("/slug-check", response_model=SlugCheckResponse, summary="Check slug availability")
def slug_check(
    slug: str | None = None,
    exclude_id: uuid.UUID | None = None,
    _admin: Users = Depends(get_current_admin),
    use_case: CheckBlogSlug = Depends(get_check_blog_slug),
) -> SlugCheckResponse:
    if not slug:
        raise _http(400, "MISSING_PARAM", "slug query parameter is required")
    return SlugCheckResponse.model_validate(use_case.execute(slug, exclude_id))


# ── 21. embeds ───────────────────────────────────────────────────────────────


@router.post("/embeds/resolve", response_model=ResolvedEmbedResponse, summary="Turn a URL into a safe embed")
def resolve_embed(
    body: ResolveEmbedRequest,
    _admin: Users = Depends(get_current_admin),
    use_case: ResolveEmbed = Depends(get_resolve_embed),
) -> ResolvedEmbedResponse:
    with domain_errors():
        return ResolvedEmbedResponse.model_validate(use_case.execute(body.url))


# ── 22. link targets ─────────────────────────────────────────────────────────


@router.get("/link-targets", response_model=LinkTargetListResponse, summary="Search own posts and projects")
def link_targets(
    q: str = "",
    limit: int = Query(default=8, ge=1),
    _admin: Users = Depends(get_current_admin),
    use_case: SearchLinkTargets = Depends(get_search_link_targets),
) -> LinkTargetListResponse:
    items = use_case.execute(q, limit)
    return LinkTargetListResponse(items=[LinkTargetResponse.model_validate(i) for i in items])


# ── 2. create ────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PostDetailResponse,
             summary="Create a draft (lazy, on first autosave)")
def create_post(
    body: PostWritable,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    admin: Users = Depends(get_current_admin),
    use_case: CreateBlogPost = Depends(get_create_blog_post),
    get_use_case: GetBlogPost = Depends(get_get_blog_post),
) -> JSONResponse:
    changes = body.model_dump(exclude_unset=True)
    key = (admin.id, idempotency_key) if idempotency_key else None
    body_hash = _body_hash(changes)

    if key:
        now = time.monotonic()
        with _idempotency_lock:
            for k in [k for k, (_, _, exp) in _idempotency.items() if exp < now]:
                del _idempotency[k]
            hit = _idempotency.get(key)
        if hit:
            post_id, seen_hash, _ = hit
            if seen_hash != body_hash:
                raise _http(409, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was used with a different body.")
            with domain_errors():
                return JSONResponse(status_code=200, content=_detail(get_use_case.execute(post_id, admin.id)))

    with domain_errors():
        view = use_case.execute(admin.id, changes)
    if key:
        with _idempotency_lock:
            _idempotency[key] = (view.id, body_hash, time.monotonic() + _IDEMPOTENCY_TTL_SECONDS)
    return JSONResponse(status_code=201, content=_detail(view))


# ── 3 / 4 / 5. read, autosave, delete ────────────────────────────────────────


@router.get("/{post_id}", response_model=PostDetailResponse, summary="Load a post into the editor")
def get_post(
    post_id: uuid.UUID,
    admin: Users = Depends(get_current_admin),
    use_case: GetBlogPost = Depends(get_get_blog_post),
) -> PostDetailResponse:
    with domain_errors():
        return PostDetailResponse.model_validate(use_case.execute(post_id, admin.id))


@router.patch("/{post_id}", response_model=SaveResultResponse, summary="Autosave / update fields")
def update_post(
    post_id: uuid.UUID,
    body: UpdatePostRequest,
    admin: Users = Depends(get_current_admin),
    use_case: UpdateBlogPost = Depends(get_update_blog_post),
) -> SaveResultResponse:
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    with domain_errors():
        return SaveResultResponse.model_validate(use_case.execute(post_id, admin.id, body.version, changes))


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a never-published draft")
def delete_post(
    post_id: uuid.UUID,
    version: int = Query(..., ge=1),
    admin: Users = Depends(get_current_admin),
    use_case: DeleteBlogPost = Depends(get_delete_blog_post),
) -> Response:
    with domain_errors():
        use_case.execute(post_id, admin.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 7–12. publishing ─────────────────────────────────────────────────────────


@router.get("/{post_id}/checklist", response_model=ChecklistResponse, summary="Before-publish checklist")
def checklist(
    post_id: uuid.UUID,
    admin: Users = Depends(get_current_admin),
    use_case: GetBlogChecklist = Depends(get_blog_checklist),
) -> ChecklistResponse:
    with domain_errors():
        return ChecklistResponse.model_validate(use_case.execute(post_id, admin.id))


@router.post("/{post_id}/publish", response_model=PostDetailResponse, summary="Publish or Update")
def publish(
    post_id: uuid.UUID,
    body: VersionRequest,
    admin: Users = Depends(get_current_admin),
    use_case: PublishBlogPost = Depends(get_publish_blog_post),
) -> PostDetailResponse:
    with domain_errors():
        return PostDetailResponse.model_validate(use_case.execute(post_id, admin.id, body.version))


@router.put("/{post_id}/schedule", response_model=PostDetailResponse, summary="Schedule or reschedule")
def schedule(
    post_id: uuid.UUID,
    body: ScheduleRequest,
    admin: Users = Depends(get_current_admin),
    use_case: ScheduleBlogPost = Depends(get_schedule_blog_post),
) -> PostDetailResponse:
    with domain_errors():
        view = use_case.execute(post_id, admin.id, body.version, body.scheduled_at)
    return PostDetailResponse.model_validate(view)


@router.delete("/{post_id}/schedule", response_model=PostDetailResponse, summary="Unschedule")
def unschedule(
    post_id: uuid.UUID,
    version: int = Query(..., ge=1),
    admin: Users = Depends(get_current_admin),
    use_case: UnscheduleBlogPost = Depends(get_unschedule_blog_post),
) -> PostDetailResponse:
    with domain_errors():
        return PostDetailResponse.model_validate(use_case.execute(post_id, admin.id, version))


@router.post("/{post_id}/unpublish", response_model=PostDetailResponse, summary="Take a live post down")
def unpublish(
    post_id: uuid.UUID,
    body: VersionRequest,
    admin: Users = Depends(get_current_admin),
    use_case: UnpublishBlogPost = Depends(get_unpublish_blog_post),
) -> PostDetailResponse:
    with domain_errors():
        return PostDetailResponse.model_validate(use_case.execute(post_id, admin.id, body.version))


@router.post("/{post_id}/discard-changes", response_model=PostDetailResponse,
             summary="Reset the working copy to the live version")
def discard_changes(
    post_id: uuid.UUID,
    body: VersionRequest,
    admin: Users = Depends(get_current_admin),
    use_case: DiscardBlogChanges = Depends(get_discard_blog_changes),
) -> PostDetailResponse:
    with domain_errors():
        return PostDetailResponse.model_validate(use_case.execute(post_id, admin.id, body.version))


# ── 13. preview ──────────────────────────────────────────────────────────────


@router.get("/{post_id}/preview", response_model=PreviewResponse, summary="Render as readers will see it")
def preview(
    post_id: uuid.UUID,
    response: Response,
    source: str = Query(default="working", description="working | live"),
    admin: Users = Depends(get_current_admin),
    use_case: GetBlogPreview = Depends(get_blog_preview),
) -> PreviewResponse:
    response.headers["Cache-Control"] = "no-store"
    with domain_errors():
        return PreviewResponse.model_validate(use_case.execute(post_id, admin.id, source))


# ── 14–17. revisions ─────────────────────────────────────────────────────────


def _revision_summary(rv: RevisionView) -> dict:
    r = rv.revision
    return {
        "id": r.id,
        "kind": r.kind,
        "label": r.label,
        "word_count": r.word_count,
        "created_by": RevisionAuthor(id=r.created_by, name=r.created_by_name) if r.created_by else None,
        "created_at": r.created_at,
        "is_live": rv.is_live,
    }


@router.post("/{post_id}/revisions", response_model=RevisionSummaryResponse, status_code=201,
             summary="Save draft (manual revision)")
def create_revision(
    post_id: uuid.UUID,
    body: CreateRevisionRequest,
    admin: Users = Depends(get_current_admin),
    use_case: CreateBlogRevision = Depends(get_create_blog_revision),
) -> JSONResponse:
    with domain_errors():
        rv, created = use_case.execute(post_id, admin.id, body.version, body.label)
    content = RevisionSummaryResponse(**_revision_summary(rv)).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=content)


@router.get("/{post_id}/revisions", response_model=RevisionListResponse, summary="Revision history")
def list_revisions(
    post_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1),
    kind: str | None = Query(default=None, description="publish | manual | restore"),
    admin: Users = Depends(get_current_admin),
    use_case: ListBlogRevisions = Depends(get_list_blog_revisions),
) -> RevisionListResponse:
    with domain_errors():
        result = use_case.execute(post_id, admin.id, kind=kind, page=page, limit=limit)
    return RevisionListResponse(
        items=[RevisionSummaryResponse(**_revision_summary(rv)) for rv in result.items],
        total=result.total,
        page=result.page,
        limit=result.limit,
        total_pages=max(1, math.ceil(result.total / result.limit)),
    )


@router.get("/{post_id}/revisions/{revision_id}", response_model=RevisionDetailResponse,
            summary="One revision with its snapshot")
def get_revision(
    post_id: uuid.UUID,
    revision_id: uuid.UUID,
    admin: Users = Depends(get_current_admin),
    use_case: GetBlogRevision = Depends(get_get_blog_revision),
) -> RevisionDetailResponse:
    with domain_errors():
        rv = use_case.execute(post_id, revision_id, admin.id)
    return RevisionDetailResponse(
        **_revision_summary(rv), snapshot=rv.revision.snapshot, content_html=rv.revision.content_html
    )


@router.post("/{post_id}/revisions/{revision_id}/restore", response_model=PostDetailResponse,
             summary="Restore a revision into the working copy")
def restore_revision(
    post_id: uuid.UUID,
    revision_id: uuid.UUID,
    body: VersionRequest,
    admin: Users = Depends(get_current_admin),
    use_case: RestoreBlogRevision = Depends(get_restore_blog_revision),
) -> PostDetailResponse:
    with domain_errors():
        return PostDetailResponse.model_validate(use_case.execute(post_id, revision_id, admin.id, body.version))

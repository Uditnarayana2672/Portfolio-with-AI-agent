"""Public site endpoints (presentation layer). No login; published content only."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.v1.dependencies.providers import (
    get_engagement,
    get_get_portfolio_content,
    get_list_project_slugs,
    get_list_public_projects,
    get_newsletter,
    get_public_blog,
    get_public_comments,
    get_public_polls,
    get_public_site_repository,
    get_submit_contact_message,
)
from app.api.v1.dependencies.rate_limit import rate_limit
from app.api.v1.schemas.portfolio import PublicPortfolioContentResponse
from app.api.v1.schemas.public_site import (
    AcceptedResponse,
    BlogCardResponse,
    BlogEngagementResponse,
    BlogItemsResponse,
    BlogListResponse,
    CategoryListResponse,
    CommentCreateRequest,
    CommentListResponse,
    ContactMessageRequest,
    PollResponse,
    PollVoteRequest,
    ProjectCardResponse,
    ProjectEngagementResponse,
    ProjectListResponse,
    ProjectSlugsResponse,
    PublicBlogPostResponse,
    ReactionRequest,
    ReactionsResponse,
    RedirectListResponse,
    SubscribeRequest,
    TagListResponse,
    TokenRequest,
    ViewRequest,
)
from app.application.use_cases.portfolio.portfolio_content import GetPortfolioContent
from app.application.use_cases.public_site.blogs import BlogCard, MovedPost, PublicBlog
from app.application.use_cases.public_site.interactions import (
    AlreadyVotedError,
    CaptchaFailedError,
    CommentsClosedError,
    Engagement,
    Newsletter,
    PollClosedError,
    PublicComments,
    PublicPolls,
    SubmitContactMessage,
    TokenExpiredError,
)
from app.application.use_cases.public_site.projects import ListProjectSlugs, ListPublicProjects, ProjectCard, require_project_id
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.portfolio_document import resolve_stats
from app.domain.repositories.public_site_repository import PublicSiteRepository

router = APIRouter(tags=["Public site"])

PUBLIC_CACHE = "public, max-age=60"
_write_limit = Depends(rate_limit("public-write", 60, 3600))
_form_limit = Depends(rate_limit("public-form", 10, 3600))


def _error(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


def _not_found(exc: Exception) -> HTTPException:
    return _error(404, "NOT_FOUND", str(exc))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _project_card(card: ProjectCard) -> ProjectCardResponse:
    value, label = card.meta("card_stat_value"), card.meta("card_stat_label")
    p = card.project
    return ProjectCardResponse(
        id=p.id, title=p.title, slug=p.slug, excerpt=p.excerpt, image_url=card.image_url, tech_stack=p.tech_stack,
        category=card.meta("category") or card.meta("kicker"), status_label=card.meta("status_label"),
        card_stat={"value": value, "label": label or ""} if value else None,
        is_featured=p.is_featured, demo_url=p.demo_url, github_url=p.github_url, published_at=p.published_at,
    )


def _blog_cards(cards: list[BlogCard]) -> list[BlogCardResponse]:
    return [BlogCardResponse.model_validate(c) for c in cards]


# ── portfolio content ────────────────────────────────────────────────────────


@router.get("/portfolio-content", response_model=PublicPortfolioContentResponse, summary="Main page content")
def get_portfolio_content(
    response: Response,
    use_case: GetPortfolioContent = Depends(get_get_portfolio_content),
    repo: PublicSiteRepository = Depends(get_public_site_repository),
) -> PublicPortfolioContentResponse:
    try:
        doc = use_case.execute()
    except NotFoundError as exc:
        raise _error(404, "CONTENT_NOT_FOUND", str(exc)) from exc
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return PublicPortfolioContentResponse(
        updated_at=doc.updated_at,
        content=resolve_stats(doc.content, len(repo.list_public_projects())),
    )


# ── projects ─────────────────────────────────────────────────────────────────


@router.get("/projects", response_model=ProjectListResponse, summary="Published project list")
def list_projects(
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
    featured: bool | None = None,
    category: str | None = None,
    tech: str | None = None,
    sort: str = Query("featured", pattern="^(featured|newest)$"),
    use_case: ListPublicProjects = Depends(get_list_public_projects),
) -> ProjectListResponse:
    cards, total, categories = use_case.execute(
        featured=featured, category=category, tech=tech, sort=sort, limit=limit, offset=offset,
    )
    return ProjectListResponse(
        items=[_project_card(c) for c in cards], total=total, limit=limit, offset=offset,
        categories=[{"name": n, "count": c} for n, c in categories],
    )


@router.get("/project-slugs", response_model=ProjectSlugsResponse, summary="Every project page to build")
def project_slugs(use_case: ListProjectSlugs = Depends(get_list_project_slugs)) -> ProjectSlugsResponse:
    return ProjectSlugsResponse(items=use_case.execute())


@router.get("/projects/{slug}/engagement", response_model=ProjectEngagementResponse, summary="Live project counts")
def project_engagement(
    slug: str,
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    engagement: Engagement = Depends(get_engagement),
) -> ProjectEngagementResponse:
    try:
        project_id = require_project_id(repo, slug)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    return ProjectEngagementResponse(views=repo.project_views(project_id), reactions=engagement.reactions("project", project_id))


@router.post("/projects/{slug}/views", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Count a project view",
             dependencies=[_write_limit])
def project_view(
    slug: str,
    body: ViewRequest,
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    engagement: Engagement = Depends(get_engagement),
) -> None:
    try:
        project_id = require_project_id(repo, slug)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    engagement.record_view("project", project_id, f"/projects/{slug}", body.session_id)


@router.get("/projects/{slug}/related-blogs", response_model=BlogItemsResponse, summary="Blogs matching a project")
def project_related_blogs(
    slug: str,
    limit: int = Query(3, ge=1, le=6),
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    blog: PublicBlog = Depends(get_public_blog),
) -> BlogItemsResponse:
    match = next(((p, h) for p, h in repo.list_public_projects() if p.slug == slug), None)
    terms = match[0].tech_stack if match else []
    if match is None:
        try:
            require_project_id(repo, slug)
        except NotFoundError as exc:
            raise _not_found(exc) from exc
    return BlogItemsResponse(items=_blog_cards(blog.related_to_terms(terms, limit)))


# ── polls ────────────────────────────────────────────────────────────────────


@router.get("/project-blocks/{block_id}/poll", response_model=PollResponse, summary="Poll results")
def get_poll(
    block_id: uuid.UUID,
    session_id: str | None = Query(None, max_length=64),
    polls: PublicPolls = Depends(get_public_polls),
) -> PollResponse:
    try:
        return PollResponse.model_validate(polls.get(block_id, session_id))
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/project-blocks/{block_id}/poll/votes", response_model=PollResponse,
             status_code=status.HTTP_201_CREATED, summary="Vote", dependencies=[_write_limit])
def vote(
    block_id: uuid.UUID,
    body: PollVoteRequest,
    polls: PublicPolls = Depends(get_public_polls),
) -> PollResponse:
    try:
        return PollResponse.model_validate(polls.vote(block_id, body.option_index, body.session_id))
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except AlreadyVotedError as exc:
        raise _error(409, "ALREADY_VOTED", str(exc)) from exc
    except PollClosedError as exc:
        raise _error(409, "POLL_CLOSED", str(exc)) from exc
    except ValidationError as exc:
        raise _error(422, "VALIDATION_ERROR", str(exc)) from exc


# ── contact ──────────────────────────────────────────────────────────────────


@router.post("/contact-messages", response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Send a message", dependencies=[_form_limit])
def contact(
    body: ContactMessageRequest,
    request: Request,
    use_case: SubmitContactMessage = Depends(get_submit_contact_message),
) -> AcceptedResponse:
    try:
        use_case.execute(
            name=body.name, email=str(body.email), subject=body.subject, message=body.message,
            token=body.turnstile_token, ip=_client_ip(request), honeypot=body.website,
        )
    except CaptchaFailedError as exc:
        raise _error(400, "CAPTCHA_FAILED", str(exc)) from exc
    return AcceptedResponse(status="received")


# ── blog ─────────────────────────────────────────────────────────────────────


@router.get("/blogs", response_model=BlogListResponse, summary="List and search published posts")
def list_blogs(
    q: str | None = Query(None, max_length=120),
    category: str | None = None,
    tag: str | None = None,
    exclude: str | None = None,
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
    blog: PublicBlog = Depends(get_public_blog),
) -> BlogListResponse:
    cards, total = blog.list(q=(q or "").strip() or None, category=category, tag=tag, exclude=exclude, limit=limit, offset=offset)
    return BlogListResponse(items=_blog_cards(cards), total=total, limit=limit, offset=offset)


@router.get("/blog-categories", response_model=CategoryListResponse, summary="Categories with counts")
def blog_categories(blog: PublicBlog = Depends(get_public_blog)) -> CategoryListResponse:
    return CategoryListResponse(items=blog.categories())


@router.get("/blog-tags", response_model=TagListResponse, summary="Tags with counts")
def blog_tags(blog: PublicBlog = Depends(get_public_blog)) -> TagListResponse:
    return TagListResponse(items=blog.tags())


@router.get("/blog-redirects", response_model=RedirectListResponse, summary="Old to new post addresses")
def blog_redirects(blog: PublicBlog = Depends(get_public_blog)) -> dict:
    return {"items": blog.redirects()}


@router.get("/blogs/{slug}", response_model=PublicBlogPostResponse, summary="A published post")
def get_blog(slug: str, blog: PublicBlog = Depends(get_public_blog)):
    try:
        public, post = blog.get(slug)
    except MovedPost as moved:
        return RedirectResponse(url=f"/api/v1/blogs/{moved.slug}", status_code=status.HTTP_301_MOVED_PERMANENTLY)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    return PublicBlogPostResponse(
        **{**public.__dict__, "toc": [t.__dict__ if hasattr(t, "__dict__") else t for t in public.toc]},
        excerpt=post.excerpt,
        allow_comments=post.allow_comments,
    )


@router.get("/blogs/{slug}/related", response_model=BlogItemsResponse, summary="Related posts")
def related_blogs(
    slug: str,
    limit: int = Query(3, ge=1, le=6),
    blog: PublicBlog = Depends(get_public_blog),
) -> BlogItemsResponse:
    try:
        return BlogItemsResponse(items=_blog_cards(blog.related(slug, limit)))
    except NotFoundError as exc:
        raise _not_found(exc) from exc


def _post_id(blog: PublicBlog, slug: str) -> uuid.UUID:
    try:
        return blog.require_id(slug)
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/blogs/{slug}/engagement", response_model=BlogEngagementResponse, summary="Live post counts")
def blog_engagement(
    slug: str,
    blog: PublicBlog = Depends(get_public_blog),
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    engagement: Engagement = Depends(get_engagement),
) -> BlogEngagementResponse:
    post_id = _post_id(blog, slug)
    return BlogEngagementResponse(
        views=repo.blog_views(post_id),
        comment_count=len(repo.approved_comments(post_id)),
        reactions=engagement.reactions("blog", post_id),
    )


@router.post("/blogs/{slug}/views", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Count a post view",
             dependencies=[_write_limit])
def blog_view(
    slug: str,
    body: ViewRequest,
    blog: PublicBlog = Depends(get_public_blog),
    engagement: Engagement = Depends(get_engagement),
) -> None:
    engagement.record_view("blog", _post_id(blog, slug), f"/blog/{slug}", body.session_id)


@router.post("/blogs/{slug}/reactions", response_model=ReactionsResponse, summary="React to a post",
             dependencies=[_write_limit])
def blog_reaction(
    slug: str,
    body: ReactionRequest,
    blog: PublicBlog = Depends(get_public_blog),
    engagement: Engagement = Depends(get_engagement),
) -> ReactionsResponse:
    try:
        counts = engagement.react("blog", _post_id(blog, slug), body.reaction_type, body.session_id)
    except ValidationError as exc:
        raise _error(422, "VALIDATION_ERROR", str(exc)) from exc
    return ReactionsResponse(slug=slug, reactions=counts)


@router.get("/blogs/{slug}/comments", response_model=CommentListResponse, summary="Approved comments")
def list_comments(
    slug: str,
    blog: PublicBlog = Depends(get_public_blog),
    comments: PublicComments = Depends(get_public_comments),
) -> CommentListResponse:
    items = comments.list(_post_id(blog, slug))
    return CommentListResponse(items=items, total=len(items))


@router.post("/blogs/{slug}/comments", response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Submit a comment for review", dependencies=[_form_limit])
def add_comment(
    slug: str,
    body: CommentCreateRequest,
    request: Request,
    blog: PublicBlog = Depends(get_public_blog),
    comments: PublicComments = Depends(get_public_comments),
) -> AcceptedResponse:
    post_id = _post_id(blog, slug)
    try:
        comments.add(
            post_id=post_id, comments_open=blog.comments_open(slug), parent_id=body.parent_id,
            name=body.author_name, email=str(body.author_email) if body.author_email else None,
            content=body.content, token=body.turnstile_token, ip=_client_ip(request), honeypot=body.website,
        )
    except CommentsClosedError as exc:
        raise _error(403, "COMMENTS_CLOSED", str(exc)) from exc
    except CaptchaFailedError as exc:
        raise _error(400, "CAPTCHA_FAILED", str(exc)) from exc
    except ValidationError as exc:
        raise _error(422, "VALIDATION_ERROR", str(exc)) from exc
    return AcceptedResponse(status="pending_review")


# ── newsletter ───────────────────────────────────────────────────────────────


@router.post("/newsletter/subscriptions", response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Subscribe", dependencies=[_form_limit])
def subscribe(
    body: SubscribeRequest,
    request: Request,
    newsletter: Newsletter = Depends(get_newsletter),
) -> AcceptedResponse:
    try:
        newsletter.subscribe(email=str(body.email), token=body.turnstile_token, ip=_client_ip(request), honeypot=body.website)
    except CaptchaFailedError as exc:
        raise _error(400, "CAPTCHA_FAILED", str(exc)) from exc
    return AcceptedResponse(status="check_your_email")


@router.post("/newsletter/confirmations", response_model=AcceptedResponse, summary="Confirm a subscription",
             dependencies=[_form_limit])
def confirm(body: TokenRequest, newsletter: Newsletter = Depends(get_newsletter)) -> AcceptedResponse:
    try:
        newsletter.confirm(body.token)
    except TokenExpiredError as exc:
        raise _error(410, "TOKEN_EXPIRED", str(exc)) from exc
    return AcceptedResponse(status="confirmed")


@router.post("/newsletter/unsubscriptions", response_model=AcceptedResponse, summary="Unsubscribe",
             dependencies=[_form_limit])
def unsubscribe(body: TokenRequest, newsletter: Newsletter = Depends(get_newsletter)) -> AcceptedResponse:
    newsletter.unsubscribe(body.token)
    return AcceptedResponse(status="unsubscribed")

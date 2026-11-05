"""HTTP schemas for the public site and the admin inbox (presentation layer)."""
from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.api.v1.schemas.blog import UtcDatetime

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
SessionId = Annotated[str, StringConstraints(min_length=8, max_length=64)]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── projects ─────────────────────────────────────────────────────────────────


class CardStat(BaseModel):
    value: str
    label: str


class ProjectCardResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    image_url: str | None
    tech_stack: list[str]
    category: str | None
    status_label: str | None
    card_stat: CardStat | None
    is_featured: bool
    demo_url: str | None
    github_url: str | None
    published_at: UtcDatetime | None


class CategoryCount(BaseModel):
    name: str
    count: int


class ProjectListResponse(BaseModel):
    items: list[ProjectCardResponse]
    total: int
    limit: int
    offset: int
    categories: list[CategoryCount]


class ProjectSlugsResponse(BaseModel):
    items: list[str]


class ViewRequest(BaseModel):
    session_id: SessionId | None = None


class ReactionRequest(BaseModel):
    reaction_type: str
    session_id: SessionId | None = None


class ProjectEngagementResponse(BaseModel):
    views: int
    reactions: dict[str, int]


class ReactionsResponse(BaseModel):
    slug: str
    reactions: dict[str, int]


# ── polls ────────────────────────────────────────────────────────────────────


class PollVoteRequest(BaseModel):
    option_index: int = Field(ge=0)
    session_id: SessionId


class PollResponse(_Out):
    question: str
    status: str
    total_votes: int
    show_results: bool
    options: list[dict[str, Any]]
    my_vote: int | None


# ── blog ─────────────────────────────────────────────────────────────────────


class BlogCardResponse(_Out):
    title: str
    subtitle: str | None
    slug: str
    url: str
    excerpt: str | None
    cover: dict[str, Any] | None
    category: dict[str, Any] | None
    tags: list[dict[str, Any]]
    reading_time_min: int
    published_at: UtcDatetime | None


class BlogListResponse(BaseModel):
    items: list[BlogCardResponse]
    total: int
    limit: int
    offset: int


class BlogItemsResponse(BaseModel):
    items: list[BlogCardResponse]


class TocItem(_Out):
    id: str
    text: str
    level: int


class PublicBlogPostResponse(_Out):
    title: str
    subtitle: str | None
    slug: str
    url: str
    excerpt: str | None
    cover: dict[str, Any] | None
    category: dict[str, Any] | None
    tags: list[dict[str, Any]]
    author: dict[str, Any]
    published_at: UtcDatetime | None
    updated_at: UtcDatetime
    reading_time_min: int
    word_count: int
    allow_comments: bool
    toc: list[Any]
    content_html: str
    head: dict[str, Any]


class BlogEngagementResponse(BaseModel):
    views: int
    comment_count: int
    reactions: dict[str, int]


class CommentReply(_Out):
    id: uuid.UUID
    author_name: str
    is_author: bool
    content: str
    created_at: UtcDatetime


class CommentResponse(CommentReply):
    replies: list[CommentReply]


class CommentListResponse(BaseModel):
    items: list[CommentResponse]
    total: int


class CommentCreateRequest(BaseModel):
    author_name: Name
    author_email: EmailStr | None = None
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    parent_id: uuid.UUID | None = None
    turnstile_token: str | None = None
    website: str | None = None


class AcceptedResponse(BaseModel):
    status: str


class CategoryItem(BaseModel):
    name: str
    slug: str
    description: str | None
    post_count: int


class CategoryListResponse(BaseModel):
    items: list[CategoryItem]


class TagItem(BaseModel):
    tag: str
    count: int


class TagListResponse(BaseModel):
    items: list[TagItem]


class RedirectItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from", serialization_alias="from")
    to: str


class RedirectListResponse(BaseModel):
    items: list[RedirectItem]


# ── contact and newsletter ───────────────────────────────────────────────────


class ContactMessageRequest(BaseModel):
    name: Name
    email: EmailStr
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    source: Annotated[str, StringConstraints(max_length=60)] = "portfolio_contact"
    turnstile_token: str | None = None
    website: str | None = None


class SubscribeRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = None
    website: str | None = None


class TokenRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=8, max_length=200)]


# ── admin ────────────────────────────────────────────────────────────────────


class InboxCounts(BaseModel):
    comments_pending: int
    messages_unread: int
    subscribers_confirmed: int


class AdminCommentResponse(BaseModel):
    id: uuid.UUID
    post: dict[str, Any]
    author_name: str
    author_email: str | None
    content: str
    status: str
    parent_id: uuid.UUID | None
    created_at: UtcDatetime


class AdminCommentList(BaseModel):
    items: list[AdminCommentResponse]
    total: int


class CommentPatchRequest(BaseModel):
    status: Literal["approved", "pending"]


class CommentReplyRequest(BaseModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AdminMessageResponse(_Out):
    id: uuid.UUID
    name: str
    email: str
    subject: str
    message: str
    read: bool
    created_at: UtcDatetime


class AdminMessageList(BaseModel):
    items: list[AdminMessageResponse]
    total: int


class MessagePatchRequest(BaseModel):
    read: bool


class AdminSubscriberResponse(_Out):
    id: uuid.UUID
    email: str
    status: str
    subscribed_at: UtcDatetime
    confirmed_at: UtcDatetime | None


class AdminSubscriberList(BaseModel):
    items: list[AdminSubscriberResponse]
    total: int


class NewsletterSendRequest(BaseModel):
    version: int = Field(ge=1)


class NewsletterSendResponse(BaseModel):
    recipients: int
    post_slug: str
    status: str


class SiteBuildResponse(BaseModel):
    site: str
    state: str
    dirty_since: UtcDatetime | None
    last_triggered_at: UtcDatetime | None


class SiteBuildList(BaseModel):
    items: list[SiteBuildResponse]


class SiteBuildRequest(BaseModel):
    site: Literal["portfolio", "lighthouse"]


class FlushResponse(BaseModel):
    triggered: list[str]

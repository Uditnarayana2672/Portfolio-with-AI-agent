"""Internal blog endpoints (presentation layer).

POST /internal/blogs/publish-due — the external-cron trigger for scheduled
publishing (endpoint 23). Authenticated by the ``X-Cron-Secret`` header, not a
user JWT, and hidden from the OpenAPI docs.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.v1.dependencies.providers import get_publish_due_posts
from app.api.v1.schemas.blog import DueRunResponse
from app.application.use_cases.blog.publishing import PublishDuePosts
from app.infrastructure.config import settings

router = APIRouter(prefix="/internal/blogs", include_in_schema=False)


def require_cron_secret(x_cron_secret: str | None = Header(default=None)) -> None:
    expected = settings.BLOG_CRON_SECRET
    if not expected:
        # Not configured → the endpoint doesn't exist as far as callers know.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret")


@router.post("/publish-due", response_model=DueRunResponse)
def publish_due(
    _: None = Depends(require_cron_secret),
    use_case: PublishDuePosts = Depends(get_publish_due_posts),
) -> DueRunResponse:
    return DueRunResponse.model_validate(use_case.execute())

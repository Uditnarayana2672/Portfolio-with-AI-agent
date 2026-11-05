"""Admin activity stream endpoint (presentation layer)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_list_recent_activity
from app.api.v1.schemas.activity import ActivityItemResponse, ActivityListResponse
from app.application.use_cases.activity.list_recent_activity import ListRecentActivity
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin/activity", tags=["Activity"])


@router.get("", response_model=ActivityListResponse, summary="Recent admin activity, newest first")
def list_activity(
    limit: int = Query(default=20, ge=1, le=50),
    _admin: Users = Depends(get_current_admin),
    use_case: ListRecentActivity = Depends(get_list_recent_activity),
) -> ActivityListResponse:
    views = use_case.execute(limit)
    return ActivityListResponse(
        items=[
            ActivityItemResponse(
                id=v.id,
                action_type=v.action_type,
                category=v.category,
                description=v.description,
                entity_type=v.entity_type,
                entity_id=v.entity_id,
                entity_title=v.entity_title,
                actor=v.actor,
                link=v.link,
                created_at=v.created_at,
            )
            for v in views
        ]
    )

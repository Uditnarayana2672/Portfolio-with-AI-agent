"""User-facing endpoints.

Right now this only exposes two smoke-test endpoints for the auth chain:
  GET /api/v1/me          -> any logged-in user; returns their profile
  GET /api/v1/admin/ping  -> only role='admin'; proves the admin guard works

Real CRUD endpoints (create blog post, edit project, etc.) will be added
here later, using the same `Depends(get_current_admin)` pattern.
"""
from fastapi import APIRouter, Depends

from app.api.v1.dependencies.auth import get_current_admin, get_current_user
from app.infrastructure.persistence.orm.models import Users

router = APIRouter()


@router.get("/me")
def read_me(user: Users = Depends(get_current_user)) -> dict:
    """Return the calling user's profile. Any logged-in user can hit this."""
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "avatar_url": user.avatar_url,
        "is_blocked": user.is_blocked,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/admin/ping")
def admin_ping(admin: Users = Depends(get_current_admin)) -> dict:
    """Smoke test: only role='admin' users see {'pong': True}.
    Anyone else gets 401 (no token) or 403 (not admin)."""
    return {"pong": True, "as": admin.email}

"""FastAPI auth dependencies.

Use these in endpoint signatures to require login or admin role:

    @router.get("/me")
    def read_me(user: Users = Depends(get_current_user)):
        ...

    @router.post("/projects")
    def create_project(admin: Users = Depends(get_current_admin)):
        ...

Two layers of check:
  - `get_current_user`  -> 401 if token missing/invalid/expired,
                           403 if the user row is blocked.
  - `get_current_admin` -> everything above, plus 403 if role != 'admin'.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.infrastructure.external.supabase_auth import verify_supabase_jwt
from app.infrastructure.persistence.database import get_db
from app.infrastructure.persistence.orm.models import UserRole, Users

# HTTPBearer pulls the token out of `Authorization: Bearer <token>` and
# gives /docs a working "Authorize" button. auto_error=False lets us raise
# our own 401 (instead of the default 403) when the header is missing.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Users:
    """Return the `Users` row for the caller, or raise 401/403.

    Steps:
      1. Reject if no Authorization header was sent.
      2. Verify the JWT (signature, expiry, audience).
      3. Look up the matching row in `public.users` — created by the
         `on_auth_user_created` trigger when the user signed up.
      4. Reject if the row is missing or `is_blocked` is true.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_supabase_jwt(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(Users, payload["user_id"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile not found",
        )
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )
    return user


def get_current_admin(user: Users = Depends(get_current_user)) -> Users:
    """Require role == 'admin'. Raises 403 otherwise.

    Builds on get_current_user so token/blocked checks happen first.
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user

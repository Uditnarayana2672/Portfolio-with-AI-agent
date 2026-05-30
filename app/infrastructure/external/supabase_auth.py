"""JWT verification for Supabase Auth tokens.

Supabase signs JWTs with **asymmetric** keys (ES256 — ECDSA over P-256).
To verify, we fetch Supabase's public JWKS (JSON Web Key Set) and check the
token's signature against the public key whose `kid` matches the JWT header.

JWKS endpoint:
    https://<project>.supabase.co/auth/v1/.well-known/jwks.json

Keys rotate rarely. We cache them in memory for the process lifetime; if a
JWT references an unknown `kid` we refetch once (handles fresh rotation).

This module does NOT use SUPABASE_JWT_SECRET — that's the legacy HS256 secret,
kept in .env only for reference. Asymmetric verification needs no shared
secret on the backend.
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, TypedDict

import httpx
from jose import JWTError, jwt

from app.infrastructure.config import settings


class SupabaseTokenPayload(TypedDict):
    """Subset of fields we care about from a verified Supabase JWT."""

    user_id: uuid.UUID
    email: str | None


JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

# Algorithms we accept. Reject HS256 to prevent the "alg=none" / key-confusion
# attacks where an attacker substitutes an HMAC token signed with the public
# key as the "secret".
_ALLOWED_ALGS = {"ES256", "RS256", "EdDSA"}

_jwks_cache: dict[str, Any] | None = None
_jwks_lock = threading.Lock()


def _fetch_jwks(force_refresh: bool = False) -> dict[str, Any]:
    """Return the cached JWKS, fetching from Supabase if missing or forced."""
    global _jwks_cache
    with _jwks_lock:
        if _jwks_cache is None or force_refresh:
            response = httpx.get(JWKS_URL, timeout=10.0)
            response.raise_for_status()
            _jwks_cache = response.json()
    return _jwks_cache


def _find_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    keys = jwks.get("keys", [])
    if kid is None:
        # Token didn't specify a kid. If there's exactly one key in the set,
        # use it. Otherwise it's ambiguous — reject.
        return keys[0] if len(keys) == 1 else None
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


def verify_supabase_jwt(token: str) -> SupabaseTokenPayload:
    """Validate a Supabase JWT and return user_id + email.

    Raises `jose.JWTError` (or a subclass) for any token problem:
      - malformed header
      - unsupported / forbidden algorithm
      - no matching public key
      - bad signature, wrong audience, or expired
      - missing/invalid 'sub' claim

    Callers (FastAPI dependencies) catch JWTError and return HTTP 401.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise JWTError(f"Malformed token header: {exc}") from exc

    alg = header.get("alg")
    if alg not in _ALLOWED_ALGS:
        raise JWTError(f"Unsupported algorithm: {alg!r}")

    kid = header.get("kid")

    jwks = _fetch_jwks()
    key = _find_key(jwks, kid)
    if key is None:
        # Maybe a key rotation just happened — refresh once and retry.
        jwks = _fetch_jwks(force_refresh=True)
        key = _find_key(jwks, kid)
        if key is None:
            raise JWTError(f"No matching JWKS key for kid={kid!r}")

    payload = jwt.decode(
        token,
        key,
        algorithms=[alg],
        audience=settings.SUPABASE_JWT_AUDIENCE,
    )

    sub = payload.get("sub")
    if not sub:
        raise JWTError("Token missing 'sub' claim")

    try:
        user_id = uuid.UUID(sub)
    except (ValueError, TypeError) as exc:
        raise JWTError("Token 'sub' is not a valid UUID") from exc

    return {"user_id": user_id, "email": payload.get("email")}

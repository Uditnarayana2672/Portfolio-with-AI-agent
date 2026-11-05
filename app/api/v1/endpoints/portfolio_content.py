"""Portfolio content endpoints (presentation layer).

Admin: load and save the one document. Public: read-only copy for the site.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError as PydanticValidationError

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_get_portfolio_content, get_update_portfolio_content
from app.api.v1.schemas.portfolio import (
    MAX_DOCUMENT_BYTES,
    AdminPortfolioContentResponse,
    PortfolioDocument,
    PublicPortfolioContentResponse,
    SavedPortfolioContentResponse,
    UpdatePortfolioContentRequest,
)
from app.application.use_cases.portfolio.portfolio_content import GetPortfolioContent, UpdatePortfolioContent
from app.domain.exceptions import PortfolioContentNotFoundError, VersionConflictError
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin/portfolio-content", tags=["Portfolio content"])
public_router = APIRouter(prefix="/portfolio-content", tags=["Public portfolio content"])

_PUBLIC_CACHE = "public, max-age=60"


def _http(code: int, error: str, message: str, detail: dict | None = None) -> HTTPException:
    body: dict = {"error": error, "message": message}
    if detail:
        body["detail"] = detail
    return HTTPException(status_code=code, detail=body)


def _not_found(exc: PortfolioContentNotFoundError) -> HTTPException:
    return _http(404, "CONTENT_NOT_FOUND", str(exc))


def _field_path(loc: tuple) -> str:
    """('tech', 3, 'level') -> 'tech[3].level'."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def _validated(content: dict) -> dict:
    size = len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
    if size > MAX_DOCUMENT_BYTES:
        raise _http(413, "CONTENT_TOO_LARGE", "Portfolio content is larger than 64 KB.", {
            "size_bytes": size,
            "max_bytes": MAX_DOCUMENT_BYTES,
        })
    try:
        document = PortfolioDocument.model_validate(content)
    except PydanticValidationError as exc:
        fields = [{"path": _field_path(e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise _http(422, "INVALID_CONTENT", "Some fields need fixing before saving.", {"fields": fields}) from exc
    return document.model_dump(mode="json")


@router.get("", response_model=AdminPortfolioContentResponse, summary="Load the portfolio content for editing")
def get_admin_content(
    _admin: Users = Depends(get_current_admin),
    use_case: GetPortfolioContent = Depends(get_get_portfolio_content),
) -> AdminPortfolioContentResponse:
    try:
        doc = use_case.execute()
    except PortfolioContentNotFoundError as exc:
        raise _not_found(exc) from exc
    return AdminPortfolioContentResponse(
        version=doc.version,
        updated_at=doc.updated_at,
        updated_by_name=doc.updated_by_name,
        content=doc.content,
    )


@router.put("", response_model=SavedPortfolioContentResponse, summary="Save the portfolio content; live immediately")
def update_content(
    body: UpdatePortfolioContentRequest,
    admin: Users = Depends(get_current_admin),
    use_case: UpdatePortfolioContent = Depends(get_update_portfolio_content),
) -> SavedPortfolioContentResponse:
    content = _validated(body.content)
    try:
        saved = use_case.execute(expected_version=body.version, content=content, actor_id=admin.id)
    except PortfolioContentNotFoundError as exc:
        raise _not_found(exc) from exc
    except VersionConflictError as exc:
        raise _http(
            409,
            "VERSION_CONFLICT",
            "This content was changed somewhere else. Reload to get the latest version.",
            {
                "current_version": exc.current_version,
                "updated_at": exc.updated_at.isoformat() if exc.updated_at else None,
            },
        ) from exc
    doc = saved.document
    return SavedPortfolioContentResponse(
        version=doc.version,
        updated_at=doc.updated_at,
        updated_by_name=doc.updated_by_name,
        content=doc.content,
        changed_sections=saved.changed_sections,
    )


@public_router.get("", response_model=PublicPortfolioContentResponse, summary="Read the portfolio content (public)")
def get_public_content(
    response: Response,
    use_case: GetPortfolioContent = Depends(get_get_portfolio_content),
) -> PublicPortfolioContentResponse:
    try:
        doc = use_case.execute()
    except PortfolioContentNotFoundError as exc:
        raise _not_found(exc) from exc
    response.headers["Cache-Control"] = _PUBLIC_CACHE
    return PublicPortfolioContentResponse(updated_at=doc.updated_at, content=doc.content)

"""Admin forms endpoints (presentation layer).

Thin controller: parse the request, call the use case, serialize the result.
No business logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import get_list_forms
from app.api.v1.schemas.form import FormSummaryResponse
from app.application.use_cases.forms.list_forms import ListForms
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(prefix="/admin/forms", tags=["Forms"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[FormSummaryResponse],
    summary="List forms",
    description=(
        "Return all forms owned by the current admin, ordered by creation date "
        "descending. Pass `?search=` to filter by name (case-insensitive substring)."
    ),
)
def list_forms(
    search: str | None = None,
    current_admin: Users = Depends(get_current_admin),
    use_case: ListForms = Depends(get_list_forms),
) -> list[FormSummaryResponse]:
    results = use_case.execute(author_id=current_admin.id, search=search)
    return [
        FormSummaryResponse(
            id=f.id,
            name=f.name,
            form_type=f.form_type,
            created_at=f.created_at,
        )
        for f in results
    ]

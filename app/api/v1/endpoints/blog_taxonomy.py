"""Admin blog categories and tags endpoints (presentation layer).

Endpoints 18–20 of "New Blog Post API.md".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.dependencies.auth import get_current_admin
from app.api.v1.dependencies.providers import (
    get_create_blog_category,
    get_list_blog_categories,
    get_list_blog_tags,
)
from app.api.v1.endpoints.blogs import domain_errors
from app.api.v1.schemas.blog import (
    CategoryListResponse,
    CategoryResponse,
    CreateCategoryRequest,
    TagCount,
    TagListResponse,
)
from app.application.use_cases.blog.taxonomy import CreateBlogCategory, ListBlogCategories, ListBlogTags
from app.infrastructure.persistence.orm.models import Users

router = APIRouter(tags=["Blog editor"])


@router.get("/admin/blog-categories", response_model=CategoryListResponse, summary="List categories")
def list_categories(
    _admin: Users = Depends(get_current_admin),
    use_case: ListBlogCategories = Depends(get_list_blog_categories),
) -> CategoryListResponse:
    return CategoryListResponse(items=[CategoryResponse.model_validate(c) for c in use_case.execute()])


@router.post("/admin/blog-categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a category from the editor")
def create_category(
    body: CreateCategoryRequest,
    _admin: Users = Depends(get_current_admin),
    use_case: CreateBlogCategory = Depends(get_create_blog_category),
) -> CategoryResponse:
    with domain_errors():
        return CategoryResponse.model_validate(use_case.execute(body.name, body.description))


@router.get("/admin/blog-tags", response_model=TagListResponse, summary="Tag autocomplete")
def list_tags(
    q: str = "",
    limit: int = Query(default=10, ge=1),
    _admin: Users = Depends(get_current_admin),
    use_case: ListBlogTags = Depends(get_list_blog_tags),
) -> TagListResponse:
    return TagListResponse(items=[TagCount(tag=t, count=n) for t, n in use_case.execute(q, limit)])

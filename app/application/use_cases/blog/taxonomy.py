"""Blog taxonomy use cases (application layer): categories and tags."""
from __future__ import annotations

from app.domain.blog.slug import slugify
from app.domain.entities.blog_post import BlogCategory
from app.domain.exceptions import BlogRuleError, InvalidStateError
from app.domain.repositories.blog_category_repository import BlogCategoryRepository
from app.domain.repositories.blog_post_repository import BlogPostRepository
from app.application.use_cases.blog.post_workflow import normalize_tag

CATEGORY_NAME_RANGE = (2, 40)
TAG_LIMIT_MAX = 50


class ListBlogCategories:
    def __init__(self, repo: BlogCategoryRepository) -> None:
        self._repo = repo

    def execute(self) -> list[BlogCategory]:
        return self._repo.list_with_counts()


class CreateBlogCategory:
    def __init__(self, repo: BlogCategoryRepository) -> None:
        self._repo = repo

    def execute(self, name: str, description: str | None) -> BlogCategory:
        name = " ".join((name or "").split())
        if not CATEGORY_NAME_RANGE[0] <= len(name) <= CATEGORY_NAME_RANGE[1]:
            raise BlogRuleError(
                "VALIDATION_ERROR",
                f"Category names are {CATEGORY_NAME_RANGE[0]}–{CATEGORY_NAME_RANGE[1]} characters.",
                {"fields": {"name": "length"}},
            )
        slug = slugify(name)
        if len(slug) < 2:
            raise BlogRuleError("VALIDATION_ERROR", "Use letters or numbers in the name.",
                                {"fields": {"name": "invalid"}})
        existing = self._repo.find_by_name_or_slug(name, slug)
        if existing is not None:
            raise InvalidStateError("CATEGORY_EXISTS", f"'{existing.name}' already exists.",
                                    {"existing": {"id": str(existing.id), "name": existing.name,
                                                  "slug": existing.slug}})
        return self._repo.add(name=name, slug=slug, description=(description or "").strip() or None)


class ListBlogTags:
    def __init__(self, repo: BlogPostRepository) -> None:
        self._repo = repo

    def execute(self, query: str | None, limit: int) -> list[tuple[str, int]]:
        return self._repo.list_tags(normalize_tag(query or ""), max(1, min(limit, TAG_LIMIT_MAX)))

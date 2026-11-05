"""SQLAlchemy implementation of BlogCategoryRepository (infrastructure layer)."""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.domain.entities.blog_post import BlogCategory
from app.domain.repositories.blog_category_repository import BlogCategoryRepository
from app.infrastructure.persistence.orm.models import BlogCategories, BlogPosts, BlogStatus


class SqlAlchemyBlogCategoryRepository(BlogCategoryRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_with_counts(self) -> list[BlogCategory]:
        published = func.count(case((BlogPosts.status == BlogStatus.PUBLISHED, 1)))
        stmt = (
            select(BlogCategories, func.count(BlogPosts.id), published)
            .outerjoin(BlogPosts, BlogPosts.category_id == BlogCategories.id)
            .group_by(BlogCategories.id)
            .order_by(BlogCategories.sort_order, BlogCategories.name)
        )
        return [self._to_entity(row, total, pub) for row, total, pub in self._db.execute(stmt).all()]

    def get(self, category_id: uuid.UUID) -> BlogCategory | None:
        row = self._db.get(BlogCategories, category_id)
        return self._to_entity(row) if row else None

    def find_by_name_or_slug(self, name: str, slug: str) -> BlogCategory | None:
        row = self._db.scalar(
            select(BlogCategories).where(
                or_(func.lower(BlogCategories.name) == name.lower(), BlogCategories.slug == slug)
            )
        )
        return self._to_entity(row) if row else None

    def add(self, *, name: str, slug: str, description: str | None) -> BlogCategory:
        next_order = (self._db.scalar(select(func.max(BlogCategories.sort_order))) or 0) + 1
        row = BlogCategories(name=name, slug=slug, description=description, sort_order=next_order)
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return self._to_entity(row)

    @staticmethod
    def _to_entity(row: BlogCategories, post_count: int = 0, published_count: int = 0) -> BlogCategory:
        return BlogCategory(
            id=row.id, name=row.name, slug=row.slug, description=row.description,
            sort_order=row.sort_order, created_at=row.created_at,
            post_count=post_count, published_count=published_count,
        )

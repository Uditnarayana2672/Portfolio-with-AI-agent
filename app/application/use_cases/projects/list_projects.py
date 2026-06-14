"""ListProjects use case (application layer)."""
from __future__ import annotations

from app.application.dtos.project import (
    ALLOWED_LIST_STATUS,
    ListProjectsCommand,
    ListProjectsResult,
    ProjectSummaryResult,
)
from app.domain.exceptions import ValidationError
from app.domain.repositories.project_repository import ProjectRepository


class ListProjects:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, cmd: ListProjectsCommand) -> ListProjectsResult:
        page = max(1, cmd.page)
        page_size = min(max(1, cmd.page_size), 100)

        if cmd.status is not None and cmd.status not in ALLOWED_LIST_STATUS:
            raise ValidationError(
                f"status {cmd.status!r} is not valid. "
                f"Allowed: {sorted(ALLOWED_LIST_STATUS)}"
            )

        search = cmd.search.strip() if cmd.search else None
        search = search or None

        projects, total = self._repo.list_projects(
            author_id=cmd.author_id,
            status_filter=cmd.status,
            search=search,
            page=page,
            page_size=page_size,
        )

        return ListProjectsResult(
            items=[
                ProjectSummaryResult(
                    id=p.id,
                    title=p.title,
                    slug=p.slug,
                    excerpt=p.excerpt,
                    thumbnail_url=p.thumbnail_url,
                    template_id=p.template_id,
                    status=p.status,
                    is_featured=p.is_featured,
                    views=p.views,
                    tech_stack=p.tech_stack,
                    github_url=p.github_url,
                    demo_url=p.demo_url,
                    published_at=p.published_at,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                )
                for p in projects
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

"""ListProjects use case (application layer)."""
from __future__ import annotations

from app.application.dtos.project import (
    ALLOWED_LIST_STATUS,
    ALLOWED_SORT_BY,
    ALLOWED_TEMPLATE_IDS,
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

        if cmd.template_id is not None and cmd.template_id not in ALLOWED_TEMPLATE_IDS:
            raise ValidationError(
                f"template_id {cmd.template_id!r} is not valid. "
                f"Allowed: {sorted(ALLOWED_TEMPLATE_IDS)}"
            )

        sort_by = cmd.sort_by if cmd.sort_by in ALLOWED_SORT_BY else "created_at"
        sort_dir = cmd.sort_dir.lower() if cmd.sort_dir.lower() in ("asc", "desc") else "desc"

        search = cmd.search.strip() if cmd.search else None
        search = search or None

        projects, reactions_counts, total = self._repo.list_projects(
            author_id=cmd.author_id,
            status_filter=cmd.status,
            search=search,
            page=page,
            page_size=page_size,
            template_id=cmd.template_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
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
                    reactions_count=reactions_counts[i],
                    tech_stack=p.tech_stack,
                    github_url=p.github_url,
                    demo_url=p.demo_url,
                    published_at=p.published_at,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                )
                for i, p in enumerate(projects)
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

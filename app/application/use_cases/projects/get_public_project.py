"""GetPublicProject use case (application layer).

Loads a *published*, publicly-visible project by slug for the unauthenticated
public detail page. Bumps the view counter, attaches reaction counts, and
resolves the prev/next-project footer links. No SQL, no HTTP, no framework
imports.
"""
from __future__ import annotations

from app.application.dtos.project import (
    BlockResult,
    PublicProjectNeighbor,
    PublicProjectResult,
)
from app.domain.exceptions import NotFoundError
from app.domain.repositories.project_repository import ProjectRepository


class GetPublicProject:
    def __init__(self, *, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, slug: str) -> PublicProjectResult:
        pair = self._repo.get_published_by_slug(slug)
        if pair is None:
            raise NotFoundError(f"Project '{slug}' not found.")
        project, blocks = pair

        # Count this visit. Best-effort: a failure here should not hide the page,
        # but since the whole request shares one transaction we let the repo bump
        # and reflect the new total in the response.
        new_views = self._repo.increment_views(project.id)

        reactions = self._repo.get_reaction_counts(project.id)
        prev_n, next_n = self._resolve_neighbors(slug)

        return PublicProjectResult(
            id=project.id,
            title=project.title,
            slug=project.slug,
            excerpt=project.excerpt,
            thumbnail_url=project.thumbnail_url,
            tech_stack=project.tech_stack,
            template_id=project.template_id,
            github_url=project.github_url,
            demo_url=project.demo_url,
            views=new_views,
            seo=project.seo,
            meta=project.meta,
            blocks=[
                BlockResult(
                    id=b.id,
                    project_id=b.project_id,
                    block_type=b.block_type,
                    position=b.position,
                    config=b.config,
                    created_at=b.created_at,
                    updated_at=b.updated_at,
                )
                for b in blocks
            ],
            reactions=reactions,
            published_at=project.published_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
            prev_project=prev_n,
            next_project=next_n,
        )

    def _resolve_neighbors(
        self, slug: str
    ) -> tuple[PublicProjectNeighbor | None, PublicProjectNeighbor | None]:
        """Find the projects published just before/after the current one.

        Ordered newest-first; ``next`` is the newer project (toward the top of
        the list) and ``prev`` is the older one, matching a typical "← newer /
        older →" reading order. Returns (prev, next)."""
        published = self._repo.list_published_brief()
        idx = next((i for i, p in enumerate(published) if p.slug == slug), None)
        if idx is None:
            return None, None

        newer = published[idx - 1] if idx - 1 >= 0 else None
        older = published[idx + 1] if idx + 1 < len(published) else None

        def to_neighbor(p) -> PublicProjectNeighbor | None:
            if p is None:
                return None
            return PublicProjectNeighbor(
                title=p.title,
                slug=p.slug,
                excerpt=p.excerpt,
                thumbnail_url=p.thumbnail_url,
            )

        return to_neighbor(older), to_neighbor(newer)

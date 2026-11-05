"""Public project lists and related content (application layer)."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.project import Project
from app.domain.exceptions import NotFoundError
from app.domain.repositories.public_site_repository import PublicSiteRepository


@dataclass(frozen=True)
class ProjectCard:
    project: Project
    image_url: str | None

    def meta(self, key: str) -> str | None:
        value = (self.project.meta or {}).get(key)
        return value if isinstance(value, str) and value.strip() else None


class ListPublicProjects:
    def __init__(self, repo: PublicSiteRepository) -> None:
        self._repo = repo

    def execute(
        self, *, featured: bool | None, category: str | None, tech: str | None, sort: str, limit: int, offset: int,
    ) -> tuple[list[ProjectCard], int, list[tuple[str, int]]]:
        cards = [ProjectCard(p, p.thumbnail_url or hero) for p, hero in self._repo.list_public_projects()]

        counts: dict[str, int] = {}
        for card in cards:
            name = card.meta("category")
            if name:
                counts[name] = counts.get(name, 0) + 1

        if featured is not None:
            cards = [c for c in cards if c.project.is_featured is featured]
        if category:
            cards = [c for c in cards if c.meta("category") == category]
        if tech:
            wanted = tech.lower()
            cards = [c for c in cards if wanted in (t.lower() for t in c.project.tech_stack)]
        if sort == "featured":
            cards = sorted(cards, key=lambda c: not c.project.is_featured)  # stable: newest within each group

        return cards[offset: offset + limit], len(cards), sorted(counts.items())


class ListProjectSlugs:
    def __init__(self, repo: PublicSiteRepository) -> None:
        self._repo = repo

    def execute(self) -> list[str]:
        return self._repo.project_slugs()


def require_project_id(repo: PublicSiteRepository, slug: str):
    project_id = repo.project_id_by_slug(slug)
    if project_id is None:
        raise NotFoundError(f"Project '{slug}' not found.")
    return project_id

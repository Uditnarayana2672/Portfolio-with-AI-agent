"""CheckSlugAvailability use case (application layer).

Normalizes the candidate slug, checks reserved words, then queries the DB
to determine availability. No HTTP, no FastAPI imports here.
"""
from __future__ import annotations

import re

from app.application.dtos.project import CheckSlugCommand, CheckSlugResult
from app.domain.exceptions import ValidationError
from app.domain.repositories.project_repository import ProjectRepository

_RESERVED_SLUGS: frozenset[str] = frozenset({
    "admin", "api", "auth", "health", "login", "logout", "me", "settings",
})


class CheckSlugAvailability:
    def __init__(self, *, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, cmd: CheckSlugCommand) -> CheckSlugResult:
        normalized = _normalize_slug(cmd.slug)
        if not normalized:
            raise ValidationError(
                "Slug must contain at least one alphanumeric character"
            )

        if normalized in _RESERVED_SLUGS:
            return CheckSlugResult(
                slug=normalized,
                available=False,
                suggested=f"{normalized}-project",
            )

        taken = (
            self._repo.slug_exists_excluding(normalized, cmd.exclude_id)
            if cmd.exclude_id is not None
            else self._repo.slug_exists(normalized)
        )

        if not taken:
            return CheckSlugResult(slug=normalized, available=True, suggested=None)

        return CheckSlugResult(
            slug=normalized,
            available=False,
            suggested=self._find_suggestion(normalized),
        )

    def _find_suggestion(self, base: str) -> str:
        n = 2
        while True:
            candidate = f"{base}-{n}"
            if not self._repo.slug_exists(candidate):
                return candidate
            n += 1


def _normalize_slug(slug: str) -> str:
    """Lowercase, spaces/underscores → hyphens, strip non-alphanumeric, collapse hyphens."""
    s = slug.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")

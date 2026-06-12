"""CreateProject use case (application layer).

Validates the command, derives/resolves the slug, persists the draft project,
and records the creation in the activity log. No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

import re

from app.application.dtos.project import (
    ALLOWED_TEMPLATE_IDS,
    ALLOWED_VISIBILITY,
    CreateProjectCommand,
    CreateProjectResult,
    SeoInput,
)
from app.domain.exceptions import ValidationError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.project_repository import NewProject, ProjectRepository


class CreateProject:
    def __init__(
        self,
        *,
        repo: ProjectRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._repo = repo
        self._activity = activity

    def execute(self, cmd: CreateProjectCommand) -> CreateProjectResult:
        if not cmd.title.strip():
            raise ValidationError("title must not be empty.")

        if cmd.template_id not in ALLOWED_TEMPLATE_IDS:
            raise ValidationError(
                f"template_id {cmd.template_id!r} is not valid. "
                f"Allowed: {sorted(ALLOWED_TEMPLATE_IDS)}"
            )

        if cmd.visibility not in ALLOWED_VISIBILITY:
            raise ValidationError(
                f"visibility {cmd.visibility!r} is not valid. "
                f"Allowed: {sorted(ALLOWED_VISIBILITY)}"
            )

        base_slug = cmd.slug.strip() if cmd.slug else self._slugify(cmd.title)
        final_slug = self._resolve_slug(base_slug)

        new = NewProject(
            title=cmd.title.strip(),
            slug=final_slug,
            excerpt=cmd.excerpt,
            tech_stack=list(cmd.tech_stack),
            template_id=cmd.template_id,
            github_url=cmd.github_url,
            demo_url=cmd.demo_url,
            status="draft",
            visibility=cmd.visibility,
            is_featured=cmd.is_featured,
            seo=self._seo_to_dict(cmd.seo),
            author_id=cmd.author_id,
        )

        project = self._repo.add(new)

        self._activity.record(
            action_type="project_created",
            description=f"Project '{project.title}' created as draft.",
            entity_type="project",
            entity_id=project.id,
            entity_title=project.title,
            performed_by=cmd.author_id,
        )

        return CreateProjectResult(
            id=project.id,
            title=project.title,
            slug=project.slug,
            excerpt=project.excerpt,
            thumbnail_url=project.thumbnail_url,
            tech_stack=project.tech_stack,
            template_id=project.template_id,
            github_url=project.github_url,
            demo_url=project.demo_url,
            status=project.status,
            visibility=project.visibility,
            is_featured=project.is_featured,
            views=project.views,
            seo=project.seo,
            author_id=project.author_id,
            published_at=project.published_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    @staticmethod
    def _slugify(title: str) -> str:
        """Convert a title to a URL-safe slug: lowercase, non-alphanumeric stripped,
        whitespace/underscores collapsed to single hyphens."""
        slug = title.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        return slug or "project"

    def _resolve_slug(self, base: str) -> str:
        """Return ``base`` if free, otherwise ``base-2``, ``base-3``, … until one is free."""
        if not self._repo.slug_exists(base):
            return base
        n = 2
        while True:
            candidate = f"{base}-{n}"
            if not self._repo.slug_exists(candidate):
                return candidate
            n += 1

    @staticmethod
    def _seo_to_dict(seo: SeoInput) -> dict:
        return {
            "meta_title": seo.meta_title,
            "meta_description": seo.meta_description,
            "og_image_url": seo.og_image_url,
            "canonical_url": seo.canonical_url,
        }

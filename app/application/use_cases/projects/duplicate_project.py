"""DuplicateProject use case (application layer).

Copies an existing project (with all its blocks) into a new draft. Slug
collision for an explicitly-provided slug is surfaced as SlugTakenError;
auto-derived slugs resolve silently with numeric suffixes. All blocks are
deep-copied in the same request-scoped transaction — if any insert fails the
whole operation rolls back (get_db commits only on full success).
"""
from __future__ import annotations

import copy
import re

from app.application.dtos.project import (
    BlockResult,
    DuplicateProjectCommand,
    DuplicateProjectResult,
    GetProjectResult,
)
from app.domain.exceptions import NotFoundError, SlugTakenError, ValidationError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.block_repository import BlockRepository, NewBlock
from app.domain.repositories.project_repository import NewProject, ProjectRepository


class DuplicateProject:
    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        block_repo: BlockRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._project_repo = project_repo
        self._block_repo = block_repo
        self._activity = activity

    def execute(self, cmd: DuplicateProjectCommand) -> DuplicateProjectResult:
        pair = self._project_repo.get_with_blocks(cmd.source_id)
        if pair is None:
            raise NotFoundError("Project to duplicate not found")
        src_project, src_blocks = pair

        new_title = self._resolve_title(cmd.new_title, src_project.title)
        new_slug = self._resolve_slug(cmd.new_slug, new_title)

        seo = copy.deepcopy(src_project.seo)
        seo["canonical_url"] = None

        new = NewProject(
            title=new_title,
            slug=new_slug,
            excerpt=src_project.excerpt,
            thumbnail_url=src_project.thumbnail_url,
            tech_stack=list(src_project.tech_stack),
            template_id=src_project.template_id,
            github_url=src_project.github_url,
            demo_url=src_project.demo_url,
            status="draft",
            visibility=src_project.visibility,
            is_featured=False,
            seo=seo,
            author_id=cmd.author_id,
        )

        new_project = self._project_repo.add(new)

        copied_blocks: list[BlockResult] = []
        for block in src_blocks:
            saved = self._block_repo.add(
                NewBlock(
                    project_id=new_project.id,
                    block_type=block.block_type,
                    position=block.position,
                    config=copy.deepcopy(block.config),
                )
            )
            copied_blocks.append(
                BlockResult(
                    id=saved.id,
                    project_id=saved.project_id,
                    block_type=saved.block_type,
                    position=saved.position,
                    config=saved.config,
                    created_at=saved.created_at,
                    updated_at=saved.updated_at,
                )
            )

        self._activity.record(
            action_type="project_created",
            description=f"Project '{new_project.title}' created as duplicate of '{src_project.title}'.",
            entity_type="project",
            entity_id=new_project.id,
            entity_title=new_project.title,
            performed_by=cmd.author_id,
        )

        return DuplicateProjectResult(
            original_id=src_project.id,
            new_project=GetProjectResult(
                id=new_project.id,
                title=new_project.title,
                slug=new_project.slug,
                excerpt=new_project.excerpt,
                thumbnail_url=new_project.thumbnail_url,
                tech_stack=new_project.tech_stack,
                template_id=new_project.template_id,
                github_url=new_project.github_url,
                demo_url=new_project.demo_url,
                status=new_project.status,
                visibility=new_project.visibility,
                is_featured=new_project.is_featured,
                views=new_project.views,
                seo=new_project.seo,
                blocks=copied_blocks,
                author_id=new_project.author_id,
                published_at=None,
                created_at=new_project.created_at,
                updated_at=new_project.updated_at,
            ),
        )

    def _resolve_title(self, requested: str | None, original_title: str) -> str:
        if requested is None:
            return f"{original_title} (copy)"
        stripped = requested.strip()
        if not stripped:
            raise ValidationError("new_title must not be empty")
        return stripped

    def _resolve_slug(self, requested: str | None, title: str) -> str:
        if requested is not None:
            slug = requested.strip()
            if self._project_repo.slug_exists(slug):
                suggested = self._find_suggestion(slug)
                raise SlugTakenError(slug=slug, suggested=suggested)
            return slug
        base = _slugify(title)
        return self._find_free_slug(base)

    def _find_free_slug(self, base: str) -> str:
        if not self._project_repo.slug_exists(base):
            return base
        return self._find_suggestion(base)

    def _find_suggestion(self, base: str) -> str:
        n = 2
        while True:
            candidate = f"{base}-{n}"
            if not self._project_repo.slug_exists(candidate):
                return candidate
            n += 1


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or "project"

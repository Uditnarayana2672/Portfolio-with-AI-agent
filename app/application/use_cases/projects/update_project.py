"""UpdateProject use case (application layer).

Validates the command, applies partial changes, handles publish/unpublish
timestamps, merges SEO fields, and records the update in the activity log.
No SQL, no HTTP, no framework imports.
"""
from __future__ import annotations

import datetime
import uuid

from app.application.dtos.project import (
    ALLOWED_TEMPLATE_IDS,
    ALLOWED_UPDATE_STATUS,
    ALLOWED_VISIBILITY,
    BlockResult,
    UpdateProjectCommand,
    UpdateProjectResult,
)
from app.domain.exceptions import (
    NotFoundError,
    PermissionError,
    SlugTakenError,
    ValidationError,
)
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.project_repository import ProjectRepository


class UpdateProject:
    def __init__(
        self,
        *,
        repo: ProjectRepository,
        activity: ActivityLogRepository,
    ) -> None:
        self._repo = repo
        self._activity = activity

    def execute(self, cmd: UpdateProjectCommand) -> UpdateProjectResult:
        pair = self._repo.get_with_blocks(cmd.project_id)
        if pair is None:
            raise NotFoundError(f"Project {cmd.project_id} not found.")
        project, existing_blocks = pair

        if project.author_id != cmd.requester_id:
            raise PermissionError("You do not have access to this project.")

        fields = cmd.fields
        if not fields:
            return self._to_result(project, existing_blocks, [])

        changes: dict = {}
        warnings: list[str] = []

        if "title" in fields:
            title = fields["title"]
            if not title or not title.strip():
                raise ValidationError("title must not be empty.")
            changes["title"] = title.strip()

        if "slug" in fields:
            new_slug = fields["slug"].strip()
            if new_slug != project.slug:
                if self._repo.slug_exists_excluding(new_slug, project.id):
                    suggested = self._suggest_slug(new_slug, project.id)
                    raise SlugTakenError(new_slug, suggested)
            changes["slug"] = new_slug

        if "template_id" in fields:
            tid = fields["template_id"]
            if tid not in ALLOWED_TEMPLATE_IDS:
                raise ValidationError(
                    f"template_id must be one of: {', '.join(sorted(ALLOWED_TEMPLATE_IDS))}"
                )
            changes["template_id"] = tid

        if "visibility" in fields:
            vis = fields["visibility"]
            if vis not in ALLOWED_VISIBILITY:
                raise ValidationError(
                    f"visibility must be one of: {', '.join(sorted(ALLOWED_VISIBILITY))}"
                )
            changes["visibility"] = vis

        if "status" in fields:
            st = fields["status"]
            if st not in ALLOWED_UPDATE_STATUS:
                raise ValidationError(
                    f"status must be one of: {', '.join(sorted(ALLOWED_UPDATE_STATUS))}"
                )
            changes["status"] = st
            if st == "published" and project.published_at is None:
                changes["published_at"] = datetime.datetime.now(datetime.timezone.utc)

        for key in ("excerpt", "thumbnail_url", "github_url", "demo_url", "is_featured"):
            if key in fields:
                changes[key] = fields[key]

        if "tech_stack" in fields:
            changes["tech_stack"] = list(fields["tech_stack"])

        if "seo" in fields:
            merged_seo = {**project.seo, **fields["seo"]}
            changes["seo"] = merged_seo
            if len(merged_seo.get("meta_title") or "") > 60:
                warnings.append(
                    "meta_title exceeds 60 characters — Google may truncate it in search results"
                )
            if len(merged_seo.get("meta_description") or "") > 160:
                warnings.append(
                    "meta_description exceeds 160 characters — Google may truncate it in search results"
                )

        if not changes:
            return self._to_result(project, existing_blocks, warnings)

        updated_project, updated_blocks = self._repo.update(cmd.project_id, changes)

        self._activity.record(
            action_type="project_updated",
            description=f"Project '{updated_project.title}' updated.",
            entity_type="project",
            entity_id=updated_project.id,
            entity_title=updated_project.title,
            performed_by=cmd.requester_id,
        )

        return self._to_result(updated_project, updated_blocks, warnings)

    def _suggest_slug(self, base: str, exclude_id: uuid.UUID) -> str:
        n = 2
        while True:
            candidate = f"{base}-{n}"
            if not self._repo.slug_exists_excluding(candidate, exclude_id):
                return candidate
            n += 1

    @staticmethod
    def _to_result(project, blocks, warnings: list[str]) -> UpdateProjectResult:
        return UpdateProjectResult(
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
            author_id=project.author_id,
            published_at=project.published_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
            warnings=warnings,
        )

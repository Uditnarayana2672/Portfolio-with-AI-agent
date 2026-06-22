"""GetStatusCounts use case (application layer)."""
from __future__ import annotations

import uuid

from app.application.dtos.project import StatusCountsResult
from app.domain.repositories.project_repository import ProjectRepository


class GetStatusCounts:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    def execute(self, author_id: uuid.UUID) -> StatusCountsResult:
        counts = self._repo.get_status_counts(author_id)
        draft = counts.get("draft", 0)
        published = counts.get("published", 0)
        archived = counts.get("archived", 0)
        return StatusCountsResult(
            total=draft + published + archived,
            draft=draft,
            published=published,
            archived=archived,
        )

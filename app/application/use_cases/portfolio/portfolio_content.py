"""Read and save the portfolio content document (application layer)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.entities.portfolio_content import PortfolioContent
from app.domain.exceptions import PortfolioContentNotFoundError, VersionConflictError
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.portfolio_content_repository import PortfolioContentRepository


@dataclass(frozen=True)
class SavedPortfolioContent:
    document: PortfolioContent
    changed_sections: list[str]


def _changed_sections(old: dict, new: dict) -> list[str]:
    """Top-level sections that differ, in the new document's order."""
    return [key for key in new if old.get(key) != new[key]]


class GetPortfolioContent:
    def __init__(self, repo: PortfolioContentRepository) -> None:
        self._repo = repo

    def execute(self) -> PortfolioContent:
        document = self._repo.get()
        if document is None:
            raise PortfolioContentNotFoundError("Portfolio content has not been set up.")
        return document


class UpdatePortfolioContent:
    def __init__(self, repo: PortfolioContentRepository, activity: ActivityLogRepository) -> None:
        self._repo = repo
        self._activity = activity

    def execute(self, *, expected_version: int, content: dict, actor_id: uuid.UUID) -> SavedPortfolioContent:
        current = self._repo.get()
        if current is None:
            raise PortfolioContentNotFoundError("Portfolio content has not been set up.")
        if current.version != expected_version:
            raise VersionConflictError(current.version, current.updated_at)

        changed = _changed_sections(current.content, content)
        if not changed:
            return SavedPortfolioContent(document=current, changed_sections=[])

        updated = self._repo.update(
            expected_version=expected_version, content=content, updated_by=actor_id
        )
        if updated is None:  # lost a race with another save after the check above
            latest = self._repo.get()
            raise VersionConflictError(
                latest.version if latest else expected_version,
                latest.updated_at if latest else current.updated_at,
            )

        self._activity.record(
            action_type="portfolio_updated",
            description=f"Portfolio content updated: {', '.join(changed)}.",
            entity_type="portfolio",
            entity_title="Portfolio content",
            performed_by=actor_id,
            metadata={"changed_sections": changed, "version": updated.version},
        )
        return SavedPortfolioContent(document=updated, changed_sections=changed)

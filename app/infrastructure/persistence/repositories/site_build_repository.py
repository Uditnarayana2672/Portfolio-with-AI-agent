"""SQLAlchemy implementation of SiteBuildRepository (infrastructure layer)."""
from __future__ import annotations

import datetime
import logging

from sqlalchemy import case, func, select, update as sa_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.repositories.site_build_repository import SiteBuildRepository, SiteBuildState
from app.infrastructure.persistence.orm.models import SiteBuilds

logger = logging.getLogger("app.site_builds")

# What each activity means for the public sites. Anything else changes nothing public.
_IMMEDIATE: dict[str, tuple[str, ...]] = {
    "project_published": ("portfolio",),
    "project_deleted": ("portfolio",),
    "portfolio_updated": ("portfolio",),
    "blog_published": ("portfolio", "lighthouse"),
    "blog_updated": ("portfolio", "lighthouse"),
    "blog_archived": ("portfolio", "lighthouse"),
    "blog_deleted": ("portfolio", "lighthouse"),
    "blog_unpublished": ("portfolio", "lighthouse"),
}
QUIET_PERIOD_SECONDS = 300


def sites_for_activity(action_type: str) -> tuple[str, ...]:
    return _IMMEDIATE.get(action_type, ())


class SqlAlchemySiteBuildRepository(SiteBuildRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self) -> list[SiteBuildState]:
        rows = self._db.scalars(select(SiteBuilds).order_by(SiteBuilds.site)).all()
        return [
            SiteBuildState(r.site, r.dirty_since, r.trigger_after, r.last_triggered_at)
            for r in rows
        ]

    def mark(self, sites: tuple[str, ...], *, delay_seconds: int = 0) -> None:
        if not sites:
            return
        now = func.now()
        if delay_seconds:
            # Each further edit pushes the rebuild back, unless one is already due.
            later = now + datetime.timedelta(seconds=delay_seconds)
            trigger = case(
                (SiteBuilds.trigger_after.is_not(None) & (SiteBuilds.trigger_after <= now), SiteBuilds.trigger_after),
                else_=later,
            )
        else:
            trigger = now
        try:
            with self._db.begin_nested():
                self._db.execute(
                    sa_update(SiteBuilds)
                    .where(SiteBuilds.site.in_(sites))
                    .values(
                        dirty_since=func.coalesce(SiteBuilds.dirty_since, now),
                        trigger_after=trigger,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
        except SQLAlchemyError as exc:
            # A rebuild marker must never cost you the save it follows.
            logger.warning("Could not mark sites for rebuild: %s", exc.__class__.__name__)

    def claim_due(self, now: datetime.datetime) -> list[str]:
        return list(self._db.scalars(
            select(SiteBuilds.site)
            .where(SiteBuilds.trigger_after.is_not(None), SiteBuilds.trigger_after <= now)
            .with_for_update(skip_locked=True)
        ).all())

    def mark_triggered(self, site: str, now: datetime.datetime) -> None:
        self._db.execute(
            sa_update(SiteBuilds)
            .where(SiteBuilds.site == site)
            .values(dirty_since=None, trigger_after=None, last_triggered_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )

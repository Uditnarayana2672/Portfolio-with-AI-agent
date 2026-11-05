"""Live site rebuild status and triggering (application layer)."""
from __future__ import annotations

import datetime

from app.application.interfaces.site_services import SiteDeployer
from app.domain.repositories.site_build_repository import SiteBuildRepository, SiteBuildState

SITES = ("portfolio", "lighthouse")


def build_state(row: SiteBuildState) -> str:
    return "waiting" if row.dirty_since else ("triggered" if row.last_triggered_at else "up_to_date")


class SiteBuilds:
    def __init__(self, repo: SiteBuildRepository, deployer: SiteDeployer, clock=None) -> None:
        self._repo = repo
        self._deployer = deployer
        self._clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def status(self) -> list[SiteBuildState]:
        return self._repo.list()

    def rebuild_now(self, site: str) -> SiteBuildState:
        self._repo.mark((site,))
        if self._deployer.trigger(site):
            self._repo.mark_triggered(site, self._clock())
        return next(row for row in self._repo.list() if row.site == site)

    def flush(self) -> list[str]:
        """Ask the host to rebuild whatever is due. A failed request stays queued."""
        now = self._clock()
        triggered = []
        for site in self._repo.claim_due(now):
            if self._deployer.trigger(site):
                self._repo.mark_triggered(site, now)
                triggered.append(site)
        return triggered

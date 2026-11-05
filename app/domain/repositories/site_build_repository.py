"""SiteBuildRepository port: which public sites need rebuilding, and when."""
from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SiteBuildState:
    site: str
    dirty_since: datetime.datetime | None
    trigger_after: datetime.datetime | None
    last_triggered_at: datetime.datetime | None


class SiteBuildRepository(ABC):
    @abstractmethod
    def list(self) -> list[SiteBuildState]: ...

    @abstractmethod
    def mark(self, sites: tuple[str, ...], *, delay_seconds: int = 0) -> None:
        """Record that sites changed. Must never fail the caller's save."""

    @abstractmethod
    def claim_due(self, now: datetime.datetime) -> list[str]:
        """Lock and return the sites whose rebuild time has arrived."""

    @abstractmethod
    def mark_triggered(self, site: str, now: datetime.datetime) -> None: ...

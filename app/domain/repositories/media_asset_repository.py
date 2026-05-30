"""MediaAssetRepository port (domain layer).

Abstract contract for persisting/querying media assets. The application layer
depends on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities.media_asset import MediaAsset


@dataclass(frozen=True)
class MediaAssetListItem:
    """A listed asset paired with its uploader's display name (a join result,
    not part of the MediaAsset aggregate)."""

    asset: MediaAsset
    uploaded_by_name: str | None


@dataclass(frozen=True)
class MediaListPage:
    """One page of list results plus the total count matching the filters."""

    items: list[MediaAssetListItem]
    total: int


class MediaAssetRepository(ABC):
    @abstractmethod
    def list(
        self,
        *,
        folder: str | None,
        resource_type: str | None,
        search: str | None,
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> MediaListPage:
        """Return assets matching the filters, ordered & paginated, with the
        total count of matches (ignoring offset/limit)."""

    @abstractmethod
    def folder_stats(self) -> dict[str, int]:
        """Count of assets per folder across the WHOLE table (filters ignored),
        including an ``"all"`` grand total. Drives the sidebar pills."""

    @abstractmethod
    def type_stats(self) -> dict[str, int]:
        """Count of assets per resource_type across the WHOLE table."""

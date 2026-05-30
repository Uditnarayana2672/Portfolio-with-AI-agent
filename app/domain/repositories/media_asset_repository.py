"""MediaAssetRepository port (domain layer).

Abstract contract for persisting/querying media assets. The application layer
depends on this; the SQLAlchemy implementation lives in infrastructure.
"""
from __future__ import annotations

import uuid
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


@dataclass(frozen=True)
class NewMediaAsset:
    """The fields needed to persist a freshly uploaded asset. Distinct from the
    ``MediaAsset`` entity, which also carries server-assigned id/timestamps."""

    cloudinary_url: str | None
    public_id: str | None
    resource_type: str
    format: str | None
    width: int | None
    height: int | None
    file_size: int | None
    file_name: str | None
    folder: str
    alt_text: str | None
    source_type: str
    file_hash: str | None
    uploaded_by: uuid.UUID | None
    # Populated only for URL imports that register a remote video (YouTube),
    # where there are no binary bytes to store on Cloudinary.
    external_id: str | None = None
    thumbnail_url: str | None = None
    video_title: str | None = None
    video_duration_seconds: int | None = None


@dataclass(frozen=True)
class MediaStatsSnapshot:
    """Whole-table aggregates powering the media dashboard's stat strip.

    ``counts`` always carries the ``image``/``video``/``raw`` keys (zero-filled),
    so the frontend never has to guard for a missing resource type.
    """

    total_assets: int
    added_today: int
    counts: dict[str, int]
    used_bytes: int
    orphan_count: int


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

    @abstractmethod
    def stats(self) -> MediaStatsSnapshot:
        """Whole-table aggregates for the dashboard: total/added-today counts,
        per-type breakdown, summed storage bytes, and the orphan count."""

    @abstractmethod
    def get(self, asset_id: uuid.UUID) -> MediaAssetListItem | None:
        """Return a single asset (paired with its uploader's display name) by id,
        or None if no row matches. Powers the detail drawer."""

    @abstractmethod
    def usage_count(self, asset: MediaAsset) -> int:
        """How many content entities reference this asset (projects/blog posts
        pointing at its delivery URL). A convenience total for the drawer; the
        detailed breakdown is served separately by the usage endpoint."""

    @abstractmethod
    def find_by_hash(self, file_hash: str) -> MediaAsset | None:
        """Return an existing asset with this SHA-256, or None. Drives upload
        de-duplication (identical bytes are never re-uploaded)."""

    @abstractmethod
    def public_id_exists(self, public_id: str) -> bool:
        """True if an asset already owns this Cloudinary public_id. Drives the
        numeric-suffix rename that avoids collisions."""

    @abstractmethod
    def find_by_external_id(self, external_id: str) -> MediaAsset | None:
        """Return an existing asset registered with this external id (e.g. a
        YouTube video id), or None. De-duplicates URL imports of remote video."""

    @abstractmethod
    def add(self, new: NewMediaAsset) -> MediaAsset:
        """Persist a new asset and return it with server-assigned id/timestamps.
        Flushes so the id is available; the request's session owns the commit."""

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
class MediaUsageRef:
    """One place an asset is referenced. ``kind`` drives the icon/label and the
    admin link base (project vs blog); ``location`` is the human spot (e.g.
    "hero block", "cover", "og:image", "content", "thumbnail")."""

    kind: str            # 'project' | 'blog' | 'og'
    entity_id: uuid.UUID
    title: str | None
    location: str


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
    def find_usage(self, public_id: str) -> list[MediaUsageRef]:
        """Every place this asset's ``public_id`` appears across content:
        project thumbnails & block configs, and blog cover/og images & content.
        One row per match (a project hit via two blocks yields two refs). The
        single source of truth behind both the usage list and the drawer's
        ``usage_count`` total."""

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
    def find_by_public_id(self, public_id: str) -> MediaAsset | None:
        """Return the asset owning this Cloudinary public_id, or None. Powers the
        delete-by-public_id endpoint."""

    @abstractmethod
    def add(self, new: NewMediaAsset) -> MediaAsset:
        """Persist a new asset and return it with server-assigned id/timestamps.
        Flushes so the id is available; the request's session owns the commit."""

    @abstractmethod
    def update(
        self, asset_id: uuid.UUID, changes: dict
    ) -> MediaAssetListItem | None:
        """Apply a partial column update (the ``changes`` map) plus
        ``updated_at = now()`` to an asset, returning it re-read with its
        uploader name — or None if no row matches the id. Flushes only; the
        request's session owns the commit."""

    @abstractmethod
    def delete(self, asset_id: uuid.UUID) -> None:
        """Remove the asset row by id (no-op if already gone). Flushes only; the
        request's session owns the commit."""

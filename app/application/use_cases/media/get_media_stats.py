"""GetMediaStats use case (application layer).

Assembles the media dashboard's stat strip + storage banner from whole-table
aggregates and the configured Cloudinary plan quota. No SQL, no HTTP, no
framework imports.
"""
from __future__ import annotations

from app.application.dtos.media import (
    MediaStatsResult,
    StorageStatsView,
)
from app.domain.repositories.media_asset_repository import MediaAssetRepository

# Binary (1024-based) units — Cloudinary reports storage in these, and the
# dashboard banner is expressed the same way (e.g. 2.25 GB = 2,415,919,104 B).
_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def humanize_bytes(num: int) -> str:
    """Render a byte count as a compact human string (e.g. 1503238553 → "1.4 GB").

    Rounds to at most 2 decimals and trims trailing zeros, so whole values stay
    clean ("184 MB", not "184.00 MB").
    """
    if num <= 0:
        return "0 B"
    size = float(num)
    unit = 0
    while size >= 1024 and unit < len(_UNITS) - 1:
        size /= 1024
        unit += 1
    text = f"{size:.2f}".rstrip("0").rstrip(".")
    return f"{text} {_UNITS[unit]}"


class GetMediaStats:
    def __init__(
        self,
        repo: MediaAssetRepository,
        *,
        quota_bytes: int,
        plan: str,
    ) -> None:
        self._repo = repo
        self._quota_bytes = quota_bytes
        self._plan = plan

    def execute(self) -> MediaStatsResult:
        snap = self._repo.stats()

        used = snap.used_bytes
        quota = self._quota_bytes
        percent = round(used / quota * 100) if quota > 0 else 0

        storage = StorageStatsView(
            used_bytes=used,
            quota_bytes=quota,
            used_human=humanize_bytes(used),
            quota_human=humanize_bytes(quota),
            percent_used=percent,
            plan=self._plan,
        )

        return MediaStatsResult(
            total_assets=snap.total_assets,
            added_today=snap.added_today,
            counts=snap.counts,
            storage=storage,
            # No cleanup-run history is persisted yet, so there is nothing
            # honest to report here. Wire this up once such a table exists.
            last_cleanup=None,
        )

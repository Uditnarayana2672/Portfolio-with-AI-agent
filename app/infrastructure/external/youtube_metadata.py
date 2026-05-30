"""YouTubeMetadataProvider — resolves title/thumbnail/duration (infra layer).

Implements the ``VideoMetadataProvider`` port. Best-effort by design: it talks
only to fixed, trusted Google/YouTube hosts (the video id is the sole
user-controlled input, carried as a query param), so it is not an SSRF surface.
Any lookup failure degrades to ``None`` rather than failing the import.

  • title + thumbnail → YouTube oEmbed (no API key required).
  • duration          → YouTube Data API v3, only if ``YOUTUBE_API_KEY`` is set
                        (oEmbed does not expose duration).
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from app.application.interfaces.video_metadata import (
    VideoMetadata,
    VideoMetadataProvider,
)
from app.infrastructure.config import settings

_TIMEOUT = 6
_OEMBED = "https://www.youtube.com/oembed"
_DATA_API = "https://www.googleapis.com/youtube/v3/videos"
# ISO-8601 duration as returned by the Data API, e.g. "PT1H2M30S".
_ISO_DURATION = re.compile(
    r"P(?:(?P<d>\d+)D)?T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
)


class YouTubeMetadataProvider(VideoMetadataProvider):
    def fetch(self, video_id: str) -> VideoMetadata:
        title = self._title(video_id)
        thumbnail = self._thumbnail(video_id)
        duration = self._duration(video_id)
        return VideoMetadata(
            thumbnail_url=thumbnail, title=title, duration_seconds=duration
        )

    # ── title via oEmbed ────────────────────────────────────────────────────
    def _title(self, video_id: str) -> str | None:
        watch = f"https://www.youtube.com/watch?v={video_id}"
        query = urllib.parse.urlencode({"url": watch, "format": "json"})
        data = self._get_json(f"{_OEMBED}?{query}")
        return data.get("title") if data else None

    @staticmethod
    def _thumbnail(video_id: str) -> str:
        # Deterministic, no network — always available.
        return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    # ── duration via Data API (optional) ────────────────────────────────────
    def _duration(self, video_id: str) -> int | None:
        if not settings.YOUTUBE_API_KEY:
            return None
        query = urllib.parse.urlencode(
            {
                "id": video_id,
                "part": "contentDetails",
                "key": settings.YOUTUBE_API_KEY,
            }
        )
        data = self._get_json(f"{_DATA_API}?{query}")
        try:
            iso = data["items"][0]["contentDetails"]["duration"]
        except (KeyError, IndexError, TypeError):
            return None
        return self._iso_to_seconds(iso)

    @staticmethod
    def _iso_to_seconds(iso: str) -> int | None:
        match = _ISO_DURATION.fullmatch(iso or "")
        if not match:
            return None
        parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
        return parts["d"] * 86400 + parts["h"] * 3600 + parts["m"] * 60 + parts["s"]

    @staticmethod
    def _get_json(url: str) -> dict | None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Portfolio/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            # Best-effort: any failure (network, JSON, HTTP) → no metadata.
            return None

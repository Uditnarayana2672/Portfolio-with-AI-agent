"""YouTube URL recognition (application layer).

Decides whether an import URL is a YouTube link and extracts its 11-char video
id. Host matching is exact (so ``youtube.com.evil.com`` is NOT treated as
YouTube and instead falls through to the SSRF-validated fetch path).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
}
_SHORT_HOST = "youtu.be"
# YouTube ids are exactly 11 chars from this alphabet.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Path forms that carry the id as the first segment: /embed/<id>, /shorts/<id>…
_PATH_PREFIXES = ("embed", "shorts", "v", "live")


def parse_youtube_id(url: str) -> str | None:
    """Return the video id if ``url`` is a recognised YouTube link, else None."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == _SHORT_HOST:
        candidate = parts.path.lstrip("/").split("/", 1)[0]
        return candidate if _ID_RE.match(candidate) else None
    if host in _YOUTUBE_HOSTS:
        # /watch?v=<id>
        v = parse_qs(parts.query).get("v", [None])[0]
        if v and _ID_RE.match(v):
            return v
        segments = [s for s in parts.path.split("/") if s]
        if len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
            candidate = segments[1]
            return candidate if _ID_RE.match(candidate) else None
    return None

"""Port: remote-video metadata lookup (application layer).

For URL imports that register a hosted video (e.g. YouTube) instead of storing
bytes. The adapter resolves a title/thumbnail/duration from the provider; any
field it cannot determine comes back as None (the import must not fail just
because, say, duration needs an API key that isn't configured).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMetadata:
    thumbnail_url: str | None
    title: str | None
    duration_seconds: int | None


class VideoMetadataProvider(ABC):
    @abstractmethod
    def fetch(self, video_id: str) -> VideoMetadata:
        """Best-effort metadata for a video id. Never raises for missing fields;
        returns a ``VideoMetadata`` with Nones for anything unavailable."""

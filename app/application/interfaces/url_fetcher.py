"""Port: SSRF-safe remote URL fetcher (application layer).

Use cases depend on THIS interface, not on sockets/HTTP libraries. The concrete
adapter (`app/infrastructure/external/safe_url_fetcher.py`) is responsible for
the security-critical work: scheme allow-listing, DNS resolution + private-range
blocking, per-redirect re-validation (DNS-rebind defence), connect/read timeouts,
and a streamed download cap.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class FetchedResource:
    """The result of a safe fetch: the raw bytes plus the source's declared
    Content-Type (used only as a hint; the real type is sniffed from bytes)."""

    content: bytes
    content_type: str | None
    final_url: str


class UrlFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str, *, max_bytes: int) -> FetchedResource:
        """Fetch ``url`` safely, downloading at most ``max_bytes`` (aborting the
        stream once exceeded).

        Raises (domain exceptions):
          - ``InvalidUrlError``  — malformed URL or non-http(s) scheme.
          - ``BlockedUrlError``  — resolves to a private/loopback/link-local IP.
          - ``FileTooLargeError`` — body exceeds ``max_bytes``.
          - ``UrlFetchError``    — timeout, connection failure, too many
                                    redirects, or a 4xx/5xx from the source.
        """

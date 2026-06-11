"""SafeHttpUrlFetcher — SSRF-hardened URL fetcher (infrastructure layer).

Implements the ``UrlFetcher`` port. This is the trust boundary for fetching
arbitrary user-supplied URLs server-side, so it is deliberately strict:

  1. Scheme allow-list — only ``http`` / ``https``.
  2. DNS resolution + IP vetting — every resolved address must be globally
     routable; any private/loopback/link-local/reserved address (incl. the
     cloud metadata IP 169.254.169.254 and IPv6 equivalents / IPv4-mapped /
     6to4 / Teredo) is refused.
  3. IP pinning — we connect to the *exact* address we vetted (TLS still uses
     the hostname for SNI + cert verification), closing the DNS-rebind window
     between check and connect.
  4. Per-hop re-validation — redirects are followed manually (capped), and the
     new URL is fully re-vetted each hop, defeating redirect-to-internal.
  5. Timeout + streamed cap — connect/read timeout, and the body is read in
     chunks and aborted the moment it exceeds ``max_bytes`` (never buffered
     unboundedly).
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from app.application.interfaces.url_fetcher import FetchedResource, UrlFetcher
from app.application.use_cases.media.upload_media import humanize_limit
from app.domain.exceptions import (
    BlockedUrlError,
    FileTooLargeError,
    InvalidUrlError,
    UrlFetchError,
)
from app.infrastructure.config import settings

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_CHUNK = 64 * 1024
_USER_AGENT = "PortfolioMediaImporter/1.0"


def _unwrap(ip: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """Collapse IPv6 tunnelling/mapping forms to the embedded IPv4 so an
    attacker can't smuggle a private v4 address inside a v6 wrapper."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip.sixtofour is not None:
            return ip.sixtofour
        if ip.teredo is not None:
            return ip.teredo[1]
    return ip


def _is_blocked(ip: ipaddress._BaseAddress) -> bool:
    ip = _unwrap(ip)
    # `is_global` already excludes private/loopback/link-local/reserved, but we
    # spell the dangerous classes out too as defence in depth.
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that dials a pre-vetted IP instead of re-resolving the
    host (which would reopen the rebind window)."""

    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:  # noqa: D401
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS variant: TCP to the vetted IP, TLS SNI + cert check against the
    real hostname."""

    def __init__(
        self,
        host: str,
        ip: str,
        port: int,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        # server_hostname=self.host → SNI and hostname verification use the
        # hostname even though the socket is connected to the pinned IP.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class SafeHttpUrlFetcher(UrlFetcher):
    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_redirects: int | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else settings.URL_FETCH_TIMEOUT_SECONDS
        self._max_redirects = (
            max_redirects if max_redirects is not None else settings.URL_FETCH_MAX_REDIRECTS
        )
        self._ssl_context = ssl.create_default_context()

    def fetch(self, url: str, *, max_bytes: int) -> FetchedResource:
        current = url
        for _ in range(self._max_redirects + 1):
            scheme, host, port = self._validate_target(current)
            pinned_ip = self._resolve_and_vet(host, port)
            conn = self._open(scheme, host, pinned_ip, port)
            try:
                location, response = self._request(conn, current, host)
                if location is not None:
                    current = urljoin(current, location)
                    continue  # re-validate the next hop from scratch
                body = self._read_capped(response, max_bytes)
                content_type = response.getheader("Content-Type")
                return FetchedResource(
                    content=body, content_type=content_type, final_url=current
                )
            finally:
                conn.close()
        raise UrlFetchError("Too many redirects")

    # ── steps ───────────────────────────────────────────────────────────────
    @staticmethod
    def _validate_target(url: str) -> tuple[str, str, int]:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise InvalidUrlError(f"Unsupported URL scheme: {scheme or 'none'!r}")
        host = parts.hostname
        if not host:
            raise InvalidUrlError("URL has no host")
        port = parts.port or (443 if scheme == "https" else 80)
        return scheme, host, port

    def _resolve_and_vet(self, host: str, port: int) -> str:
        """Resolve the host and return one vetted IP to connect to. Refuses the
        whole URL if ANY resolved address is non-public (rebind defence)."""
        try:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UrlFetchError(f"DNS resolution failed for {host!r}") from exc
        if not infos:
            raise UrlFetchError(f"DNS resolution returned no records for {host!r}")

        chosen: str | None = None
        for _family, _type, _proto, _canon, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError as exc:
                raise BlockedUrlError(f"Unparseable address {ip_str!r}") from exc
            if _is_blocked(ip):
                raise BlockedUrlError(
                    f"{host!r} resolves to a disallowed address ({ip_str})"
                )
            if chosen is None:
                chosen = ip_str
        assert chosen is not None
        return chosen

    def _open(
        self, scheme: str, host: str, ip: str, port: int
    ) -> http.client.HTTPConnection:
        if scheme == "https":
            return _PinnedHTTPSConnection(
                host, ip, port, self._timeout, self._ssl_context
            )
        return _PinnedHTTPConnection(host, ip, port, self._timeout)

    def _request(
        self, conn: http.client.HTTPConnection, url: str, host: str
    ) -> tuple[str | None, http.client.HTTPResponse]:
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        try:
            conn.request(
                "GET",
                path,
                headers={
                    "Host": host,
                    "User-Agent": _USER_AGENT,
                    "Accept": "*/*",
                    "Connection": "close",
                },
            )
            response = conn.getresponse()
        except (socket.timeout, TimeoutError) as exc:
            raise UrlFetchError("Timed out fetching the URL") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise UrlFetchError(f"Failed to fetch the URL: {exc}") from exc

        if response.status in _REDIRECT_STATUSES:
            location = response.getheader("Location")
            if not location:
                raise UrlFetchError("Redirect response had no Location header")
            return location, response
        if response.status >= 400:
            raise UrlFetchError(f"Source returned HTTP {response.status}")
        return None, response

    @staticmethod
    def _read_capped(response: http.client.HTTPResponse, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = response.read(_CHUNK)
            except (socket.timeout, TimeoutError) as exc:
                raise UrlFetchError("Timed out reading the response body") from exc
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                # Abort immediately — never buffer beyond the cap.
                raise FileTooLargeError(
                    max_bytes=max_bytes, limit=humanize_limit(max_bytes)
                )
            chunks.append(chunk)
        return b"".join(chunks)

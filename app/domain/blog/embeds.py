"""Embed provider allowlist (domain layer).

Turns a pasted URL from a known provider into the iframe URL we're willing to
render. The server never trusts a client-supplied iframe ``src``: the content
validator re-runs ``resolve_embed`` and requires the stored ``embed_url`` to
match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.exceptions import BlogRuleError


@dataclass(frozen=True)
class EmbedProvider:
    id: str
    label: str
    hosts: tuple[str, ...]
    default_height: int


EMBED_PROVIDERS: tuple[EmbedProvider, ...] = (
    EmbedProvider("codepen", "CodePen", ("codepen.io",), 420),
    EmbedProvider("codesandbox", "CodeSandbox", ("codesandbox.io",), 500),
    EmbedProvider("gist", "GitHub Gist", ("gist.github.com",), 360),
    EmbedProvider("figma", "Figma", ("figma.com", "www.figma.com"), 450),
    EmbedProvider("loom", "Loom", ("loom.com", "www.loom.com"), 400),
)

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@dataclass(frozen=True)
class ResolvedEmbed:
    provider: str
    original_url: str
    embed_url: str
    height: int


def resolve_embed(url: str) -> ResolvedEmbed:
    """Map a provider URL to its embed URL, or raise ``BlogRuleError``
    (INVALID_URL / UNSUPPORTED_PROVIDER)."""
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise BlogRuleError("INVALID_URL", "Paste a full http(s) link.")
    host = parsed.netloc.lower().split(":")[0]
    path = parsed.path.rstrip("/")

    if host in _YOUTUBE_HOSTS:
        raise BlogRuleError(
            "UNSUPPORTED_PROVIDER",
            "YouTube links go in the Video block.",
            {"allowed": [p.id for p in EMBED_PROVIDERS], "hint": "Use the Video block"},
        )

    provider = next((p for p in EMBED_PROVIDERS if host in p.hosts), None)
    embed_url: str | None = None

    if provider is None:
        pass
    elif provider.id == "codepen":
        m = re.match(r"^/([^/]+)/(?:pen|full|details|embed)/([A-Za-z0-9]+)$", path)
        if m:
            embed_url = f"https://codepen.io/{m[1]}/embed/{m[2]}?default-tab=result"
    elif provider.id == "codesandbox":
        m = re.match(r"^/(?:s|embed|p/sandbox|p/devbox)/([A-Za-z0-9-]+)$", path)
        if m:
            embed_url = f"https://codesandbox.io/embed/{m[1]}"
    elif provider.id == "gist":
        m = re.match(r"^/([^/]+)/([0-9a-f]+)$", path)
        if m:
            # .pibb is GitHub's iframe-friendly rendering of a gist.
            embed_url = f"https://gist.github.com/{m[1]}/{m[2]}.pibb"
    elif provider.id == "figma":
        if re.match(r"^/(file|design|proto|board)/[A-Za-z0-9]+", path):
            clean = f"https://www.figma.com{path}"
            embed_url = f"https://www.figma.com/embed?embed_host=share&url={clean}"
    elif provider.id == "loom":
        m = re.match(r"^/(?:share|embed)/([0-9a-f]+)$", path)
        if m:
            embed_url = f"https://www.loom.com/embed/{m[1]}"

    if provider is None or embed_url is None:
        raise BlogRuleError(
            "UNSUPPORTED_PROVIDER",
            "Only CodePen, CodeSandbox, GitHub Gist, Figma and Loom links can be embedded.",
            {"allowed": [p.id for p in EMBED_PROVIDERS]},
        )
    return ResolvedEmbed(provider.id, url, embed_url, provider.default_height)

"""Blog slug rules (domain layer).

Pure functions: turning a title into a URL slug, validating a hand-edited slug,
and suggesting a free alternative. No I/O — callers pass in an ``is_taken``
predicate backed by the repository.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from collections.abc import Callable

SLUG_MIN = 3
SLUG_MAX = 80

# Paths under /blog/ that the public site and admin routes use themselves.
RESERVED_SLUGS = frozenset({
    "new", "preview", "edit", "admin", "api", "category", "tag", "tags", "page",
    "rss", "feed", "sitemap", "search", "drafts",
})

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    """Lowercase ASCII, hyphen-separated, cut at a word boundary ≤ SLUG_MAX.

    Accented letters are transliterated (é → e); anything without an ASCII
    equivalent (emoji, CJK) is dropped. May return "" — see ``fallback_slug``.
    """
    ascii_text = (
        unicodedata.normalize("NFKD", text or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if len(slug) > SLUG_MAX:
        slug = slug[:SLUG_MAX].rsplit("-", 1)[0] or slug[:SLUG_MAX]
    return slug.strip("-")


def fallback_slug() -> str:
    return f"untitled-{secrets.token_hex(3)}"


def slug_issue(slug: str) -> str | None:
    """Return why ``slug`` is unusable (``too_short`` / ``too_long`` /
    ``invalid`` / ``reserved``), or None when its shape is fine."""
    if len(slug) < SLUG_MIN:
        return "too_short"
    if len(slug) > SLUG_MAX:
        return "too_long"
    if not _SLUG_RE.match(slug):
        return "invalid"
    if slug in RESERVED_SLUGS:
        return "reserved"
    return None


def suggest_free(slug: str, is_taken: Callable[[str], bool]) -> str:
    """First of ``slug``, ``slug-2``, ``slug-3``… that isn't taken."""
    if not is_taken(slug):
        return slug
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = f"{slug[: SLUG_MAX - len(suffix)].rstrip('-')}{suffix}"
        if not is_taken(candidate):
            return candidate
        n += 1

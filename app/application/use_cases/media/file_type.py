"""Content-based file-type detection (application layer).

Sniffs the real type from magic bytes so a URL import can't lie about what it is
via the extension or a forged Content-Type header. Returns one of the
whitelisted extensions, or None when the bytes don't match any allowed type.
"""
from __future__ import annotations


def sniff_extension(content: bytes) -> str | None:
    """Return the whitelisted extension implied by the leading bytes, or None.

    Recognises exactly the upload whitelist: jpg/png/webp/gif (images),
    mp4/mov/webm (video), pdf (raw).
    """
    if len(content) < 12:
        return None
    head = content[:16]

    # ── Images ──
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"

    # ── Video / containers ──
    # ISO-BMFF (MP4/MOV): a 'ftyp' box at offset 4, brand at offset 8.
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand[:2] == b"qt":  # 'qt  ' → QuickTime
            return "mov"
        return "mp4"
    # Matroska / WebM share the EBML magic; treat as webm (our only allowed one).
    if head[:4] == b"\x1aE\xdf\xa3":
        return "webm"

    # ── Documents ──
    if head[:4] == b"%PDF":
        return "pdf"

    return None


def guess_label(content_type: str | None) -> str:
    """A human-ish 'got' label for the 415 error when the bytes aren't allowed.

    Prefers the Content-Type subtype (e.g. 'application/zip' → 'zip'); falls back
    to 'unknown'.
    """
    if not content_type:
        return "unknown"
    subtype = content_type.split(";", 1)[0].strip().split("/")[-1]
    return subtype or "unknown"

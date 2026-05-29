"""Cloudinary media storage service.

Centralises all Cloudinary access for the app. Credentials are read from
`app.core.config.settings` (which loads them from `.env`), so nothing is
hardcoded here. Import the helpers below from API endpoints / CRUD:

    from app.services.storage import upload_image, get_image_details, optimized_url
"""

from __future__ import annotations

import os
from typing import Any

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils

from app.core.config import settings

# ── Configure the SDK once at import time ──────────────────────────────────
# Prefer the three explicit fields. If only CLOUDINARY_URL is set, expose it
# via the env var the SDK parses natively (config() does not accept it as a
# kwarg). secure=True forces https:// delivery URLs.
if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
elif settings.CLOUDINARY_URL:
    os.environ.setdefault("CLOUDINARY_URL", settings.CLOUDINARY_URL)
    cloudinary.config(secure=True)
else:
    raise RuntimeError(
        "Cloudinary is not configured: set CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET "
        "(or CLOUDINARY_URL) in your .env"
    )


def upload_image(source: str, folder: str | None = None, **options: Any) -> dict[str, Any]:
    """Upload an image (file path, URL, or base64 data URI) to Cloudinary.

    Returns the raw Cloudinary upload response, which includes ``secure_url``
    and ``public_id``.
    """
    return cloudinary.uploader.upload(
        source,
        folder=folder or settings.CLOUDINARY_DEFAULT_FOLDER,
        **options,
    )


def get_image_details(public_id: str) -> dict[str, Any]:
    """Fetch stored metadata (width, height, format, bytes, ...) for an asset."""
    return cloudinary.api.resource(public_id)


def optimized_url(public_id: str) -> str:
    """Build a delivery URL with automatic format + quality optimisation.

    - ``fetch_format="auto"`` (f_auto): Cloudinary serves the best format the
      requesting browser supports (e.g. AVIF/WebP) instead of the original.
    - ``quality="auto"`` (q_auto): Cloudinary picks the smallest quality level
      that keeps the image visually unchanged.
    """
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        fetch_format="auto",
        quality="auto",
        secure=True,
    )
    return url

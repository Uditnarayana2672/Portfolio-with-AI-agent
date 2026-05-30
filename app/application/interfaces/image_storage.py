"""Port: image/media storage abstraction (application layer).

Use cases depend on THIS interface, not on Cloudinary directly. The concrete
adapter lives in `app/infrastructure/external/cloudinary_storage.py`. Swapping
storage providers (S3, local disk, …) means writing a new adapter — no use case
changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ImageStorage(ABC):
    """Contract for uploading, reading, transforming, and deleting images."""

    @abstractmethod
    def upload(
        self,
        source: str,
        *,
        folder: str | None = None,
        public_id: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Upload an image (path, URL, or data URI). Returns provider response
        including at least ``secure_url`` and ``public_id``."""

    @abstractmethod
    def get_details(self, public_id: str) -> dict[str, Any]:
        """Return stored metadata (width, height, format, bytes, …)."""

    @abstractmethod
    def optimized_url(self, public_id: str) -> str:
        """Return a delivery URL with automatic format + quality optimisation."""

    @abstractmethod
    def delete(self, public_id: str) -> dict[str, Any]:
        """Delete the asset by public id."""

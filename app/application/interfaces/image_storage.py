"""Port: image/media storage abstraction (application layer).

Use cases depend on THIS interface, not on Cloudinary directly. The concrete
adapter lives in `app/infrastructure/external/cloudinary_storage.py`. Swapping
storage providers (S3, local disk, …) means writing a new adapter — no use case
changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import IO, Any


class StorageError(Exception):
    """Raised by a storage adapter when a provider operation fails.

    Provider-agnostic so use cases can catch it without importing any SDK.
    ``request_id`` carries the provider's correlation id when available.
    """

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id


class ImageStorage(ABC):
    """Contract for uploading, reading, transforming, and deleting images."""

    @abstractmethod
    def upload(
        self,
        source: str | bytes | IO[bytes],
        *,
        folder: str | None = None,
        public_id: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Upload media (path, URL, data URI, raw bytes, or a file-like object).
        Returns the provider response including at least ``secure_url`` and
        ``public_id``. Raises ``StorageError`` on provider failure."""

    @abstractmethod
    def get_details(self, public_id: str) -> dict[str, Any]:
        """Return stored metadata (width, height, format, bytes, …)."""

    @abstractmethod
    def optimized_url(self, public_id: str) -> str:
        """Return a delivery URL with automatic format + quality optimisation."""

    @abstractmethod
    def delete(self, public_id: str) -> dict[str, Any]:
        """Delete the asset by public id."""

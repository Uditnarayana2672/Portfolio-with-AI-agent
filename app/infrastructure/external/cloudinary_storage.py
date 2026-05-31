"""Cloudinary adapter implementing the ImageStorage port (infrastructure layer).

This is the ONLY place the Cloudinary SDK is imported. Credentials come from
`settings` (loaded from .env). Application use cases receive this via the
`ImageStorage` interface and never see Cloudinary directly.
"""
from __future__ import annotations

import os
from typing import IO, Any

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from cloudinary.exceptions import Error as CloudinaryError

from app.application.interfaces.image_storage import ImageStorage, StorageError
from app.infrastructure.config import settings


class CloudinaryImageStorage(ImageStorage):
    """ImageStorage backed by Cloudinary. Configures the SDK on construction."""

    def __init__(self) -> None:
        # Prefer the three explicit fields. If only CLOUDINARY_URL is set, expose
        # it via the env var the SDK parses natively (config() does not accept it
        # as a kwarg). secure=True forces https:// delivery URLs.
        if (
            settings.CLOUDINARY_CLOUD_NAME
            and settings.CLOUDINARY_API_KEY
            and settings.CLOUDINARY_API_SECRET
        ):
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
                "Cloudinary is not configured: set CLOUDINARY_CLOUD_NAME/API_KEY/"
                "API_SECRET (or CLOUDINARY_URL) in your .env"
            )

    def upload(
        self,
        source: str | bytes | IO[bytes],
        *,
        folder: str | None = None,
        public_id: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        try:
            return cloudinary.uploader.upload(
                source,
                folder=folder or settings.CLOUDINARY_DEFAULT_FOLDER,
                public_id=public_id,
                **options,
            )
        except CloudinaryError as exc:
            # Normalise the SDK error to a provider-agnostic StorageError so the
            # use case can retry without importing Cloudinary.
            raise StorageError(str(exc), request_id=self._request_id(exc)) from exc

    def rename(
        self,
        from_public_id: str,
        to_public_id: str,
        *,
        resource_type: str = "image",
        **options: Any,
    ) -> dict[str, Any]:
        try:
            # overwrite defaults to False, so a target collision raises rather
            # than clobbering an existing asset — the caller pre-resolves names.
            return cloudinary.uploader.rename(
                from_public_id,
                to_public_id,
                resource_type=resource_type,
                **options,
            )
        except CloudinaryError as exc:
            raise StorageError(str(exc), request_id=self._request_id(exc)) from exc

    def get_details(self, public_id: str) -> dict[str, Any]:
        return cloudinary.api.resource(public_id)

    def optimized_url(self, public_id: str) -> str:
        # f_auto: best format for the browser (AVIF/WebP). q_auto: smallest
        # quality with no visible loss.
        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            fetch_format="auto",
            quality="auto",
            secure=True,
        )
        return url

    def delete(self, public_id: str) -> dict[str, Any]:
        try:
            return cloudinary.uploader.destroy(public_id)
        except CloudinaryError as exc:
            raise StorageError(str(exc), request_id=self._request_id(exc)) from exc

    @staticmethod
    def _request_id(exc: CloudinaryError) -> str | None:
        """Pull Cloudinary's correlation id off the SDK error's response, if any,
        so a StorageError can surface it for support tickets."""
        response = getattr(exc, "response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", {}) or {}
        return headers.get("X-Cld-Request-Id") or headers.get("x-cld-request-id")

"""Dependency providers — the request-scoped composition root.

This is where the onion's outer layer wires concrete infrastructure
(repositories, external services) into application use cases. Endpoints depend
on these providers via FastAPI's `Depends`, so they never construct
infrastructure themselves.

As features are added, define one provider per use case here, e.g.:

    def get_upload_media(
        db: Session = Depends(get_db),
        storage: ImageStorage = Depends(get_image_storage),
    ) -> UploadMedia:
        repo = SqlAlchemyMediaAssetRepository(db)
        return UploadMedia(repo=repo, storage=storage)
"""
from __future__ import annotations

from app.application.interfaces.image_storage import ImageStorage
from app.infrastructure.external.cloudinary_storage import CloudinaryImageStorage


def get_image_storage() -> ImageStorage:
    """Provide the configured image storage adapter (Cloudinary)."""
    return CloudinaryImageStorage()

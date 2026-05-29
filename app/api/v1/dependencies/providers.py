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

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.interfaces.image_storage import ImageStorage
from app.application.use_cases.media.list_media import ListMedia
from app.domain.repositories.media_asset_repository import MediaAssetRepository
from app.infrastructure.external.cloudinary_storage import CloudinaryImageStorage
from app.infrastructure.persistence.database import get_db
from app.infrastructure.persistence.repositories.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)


def get_image_storage() -> ImageStorage:
    """Provide the configured image storage adapter (Cloudinary)."""
    return CloudinaryImageStorage()


def get_media_repository(db: Session = Depends(get_db)) -> MediaAssetRepository:
    """Bind the SQLAlchemy media repository to the request's DB session."""
    return SqlAlchemyMediaAssetRepository(db)


def get_list_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> ListMedia:
    return ListMedia(repo=repo)

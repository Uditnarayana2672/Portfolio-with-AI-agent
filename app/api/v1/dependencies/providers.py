"""Dependency providers — the request-scoped composition root.

This is where the onion's outer layer wires concrete infrastructure
(repositories, external services) into application use cases. Endpoints depend
on these providers via FastAPI's `Depends`, so they never construct
infrastructure themselves.

TODO (implement manually):
  - get_image_storage() -> ImageStorage:
        return the configured CloudinaryImageStorage adapter (already built in
        app/infrastructure/external/cloudinary_storage.py).
  - get_media_repository(db = Depends(get_db)) -> MediaAssetRepository:
        return SqlAlchemyMediaAssetRepository(db)  # binds the request's session.
  - get_list_media(repo = Depends(get_media_repository)) -> ListMedia:
        return ListMedia(repo=repo)

  Pattern (one provider per use case), e.g. for a future upload feature:

      def get_upload_media(
          db: Session = Depends(get_db),
          storage: ImageStorage = Depends(get_image_storage),
      ) -> UploadMedia:
          repo = SqlAlchemyMediaAssetRepository(db)
          return UploadMedia(repo=repo, storage=storage)

Scaffolding you can rely on (still present and working):
    from app.infrastructure.persistence.database import get_db
    from app.infrastructure.external.cloudinary_storage import CloudinaryImageStorage
    from app.application.interfaces.image_storage import ImageStorage
"""
from __future__ import annotations

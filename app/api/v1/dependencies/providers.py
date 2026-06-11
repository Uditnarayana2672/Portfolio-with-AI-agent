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
from app.application.interfaces.url_fetcher import UrlFetcher
from app.application.interfaces.video_metadata import VideoMetadataProvider
from app.application.use_cases.media.bulk_delete_media import BulkDeleteMedia
from app.application.use_cases.media.bulk_update_media import BulkUpdateMedia
from app.application.use_cases.media.delete_media import DeleteMedia
from app.application.use_cases.media.get_media_asset import GetMediaAsset
from app.application.use_cases.media.get_media_stats import GetMediaStats
from app.application.use_cases.media.get_media_usage import GetMediaUsage
from app.application.use_cases.media.import_url_media import ImportUrlMedia
from app.application.use_cases.media.list_media import ListMedia
from app.application.use_cases.media.update_media import UpdateMedia
from app.application.use_cases.media.upload_media import UploadMedia
from app.application.use_cases.projects.create_project import CreateProject
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.media_asset_repository import MediaAssetRepository
from app.domain.repositories.project_repository import ProjectRepository
from app.infrastructure.config import settings
from app.infrastructure.external.cloudinary_storage import CloudinaryImageStorage
from app.infrastructure.external.safe_url_fetcher import SafeHttpUrlFetcher
from app.infrastructure.external.youtube_metadata import YouTubeMetadataProvider
from app.infrastructure.persistence.database import get_db
from app.infrastructure.persistence.repositories.activity_log_repository import (
    SqlAlchemyActivityLogRepository,
)
from app.infrastructure.persistence.repositories.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.infrastructure.persistence.repositories.project_repository import (
    SqlAlchemyProjectRepository,
)


def get_image_storage() -> ImageStorage:
    """Provide the configured image storage adapter (Cloudinary)."""
    return CloudinaryImageStorage()


def get_media_repository(db: Session = Depends(get_db)) -> MediaAssetRepository:
    """Bind the SQLAlchemy media repository to the request's DB session."""
    return SqlAlchemyMediaAssetRepository(db)


def get_activity_repository(db: Session = Depends(get_db)) -> ActivityLogRepository:
    """Bind the SQLAlchemy activity-log repository to the request's DB session."""
    return SqlAlchemyActivityLogRepository(db)


def get_list_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> ListMedia:
    return ListMedia(repo=repo)


def get_media_asset(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> GetMediaAsset:
    return GetMediaAsset(repo=repo)


def get_media_usage(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> GetMediaUsage:
    return GetMediaUsage(repo=repo)


def get_media_stats(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> GetMediaStats:
    # Quota/plan come from config (the PLUS plan's 2.25 GB by default); used
    # bytes are summed from the DB inside the use case.
    return GetMediaStats(
        repo=repo,
        quota_bytes=settings.CLOUDINARY_QUOTA_BYTES,
        plan=settings.CLOUDINARY_PLAN,
    )


def get_upload_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    storage: ImageStorage = Depends(get_image_storage),
) -> UploadMedia:
    return UploadMedia(repo=repo, activity=activity, storage=storage)


def get_update_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    storage: ImageStorage = Depends(get_image_storage),
) -> UpdateMedia:
    return UpdateMedia(repo=repo, storage=storage)


def get_delete_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    storage: ImageStorage = Depends(get_image_storage),
) -> DeleteMedia:
    return DeleteMedia(repo=repo, activity=activity, storage=storage)


def get_bulk_delete_media(
    delete_media: DeleteMedia = Depends(get_delete_media),
) -> BulkDeleteMedia:
    return BulkDeleteMedia(delete_media=delete_media)


def get_bulk_update_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    update_media: UpdateMedia = Depends(get_update_media),
) -> BulkUpdateMedia:
    return BulkUpdateMedia(repo=repo, update_media=update_media)


def get_url_fetcher() -> UrlFetcher:
    """Provide the SSRF-hardened URL fetcher (timeout/redirect caps from config)."""
    return SafeHttpUrlFetcher()


def get_video_metadata() -> VideoMetadataProvider:
    return YouTubeMetadataProvider()


def get_import_url_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    storage: ImageStorage = Depends(get_image_storage),
    fetcher: UrlFetcher = Depends(get_url_fetcher),
    video_metadata: VideoMetadataProvider = Depends(get_video_metadata),
) -> ImportUrlMedia:
    return ImportUrlMedia(
        repo=repo,
        activity=activity,
        storage=storage,
        fetcher=fetcher,
        video_metadata=video_metadata,
    )


# ── projects ──────────────────────────────────────────────────────────────────


def get_project_repository(db: Session = Depends(get_db)) -> ProjectRepository:
    """Bind the SQLAlchemy project repository to the request's DB session."""
    return SqlAlchemyProjectRepository(db)


def get_create_project(
    repo: ProjectRepository = Depends(get_project_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> CreateProject:
    return CreateProject(repo=repo, activity=activity)

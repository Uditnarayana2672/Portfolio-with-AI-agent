import datetime
import uuid
from unittest.mock import Mock

from app.application.use_cases.media.delete_media import DeleteMedia
from app.domain.entities.media_asset import MediaAsset
from app.domain.repositories.media_asset_repository import MediaAssetListItem


def _asset(**changes) -> MediaAsset:
    now = datetime.datetime.now(datetime.timezone.utc)
    values = {
        "id": uuid.uuid4(),
        "cloudinary_url": None,
        "public_id": None,
        "resource_type": "video",
        "format": None,
        "width": None,
        "height": None,
        "file_size": None,
        "file_name": "Example video",
        "folder": "videos",
        "alt_text": None,
        "source_type": "youtube",
        "external_id": "dQw4w9WgXcQ",
        "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "video_title": "Example video",
        "video_duration_seconds": None,
        "file_hash": None,
        "is_orphan": False,
        "uploaded_by": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(changes)
    return MediaAsset(**values)


def _use_case(repo: Mock, activity: Mock, storage: Mock) -> DeleteMedia:
    return DeleteMedia(repo=repo, activity=activity, storage=storage)


def test_execute_by_id_deletes_youtube_asset_without_storage_call() -> None:
    repo = Mock()
    activity = Mock()
    storage = Mock()
    asset = _asset()
    repo.get.return_value = MediaAssetListItem(asset=asset, uploaded_by_name=None)

    _use_case(repo, activity, storage).execute_by_id(asset.id)

    repo.get.assert_called_once_with(asset.id)
    repo.find_usage.assert_not_called()
    storage.delete.assert_not_called()
    repo.delete.assert_called_once_with(asset.id)
    activity.record.assert_called_once()


def test_execute_by_public_id_keeps_cloudinary_delete_behavior() -> None:
    repo = Mock()
    activity = Mock()
    storage = Mock()
    asset = _asset(
        cloudinary_url="https://res.cloudinary.com/demo/image/upload/portfolio/example.jpg",
        public_id="portfolio/example",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
    )
    repo.find_by_public_id.return_value = asset
    repo.find_usage.return_value = []

    _use_case(repo, activity, storage).execute("portfolio/example")

    repo.find_by_public_id.assert_called_once_with("portfolio/example")
    repo.find_usage.assert_called_once_with("portfolio/example")
    storage.delete.assert_called_once_with("portfolio/example")
    repo.delete.assert_called_once_with(asset.id)


def test_uuid_delete_route_precedes_public_id_catch_all(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "false")
    from app.api.v1.endpoints.media import router

    paths = [route.path for route in router.routes if "DELETE" in route.methods]

    assert paths == [
        "/admin/media/by-id/{asset_id}",
        "/admin/media/{public_id:path}",
    ]

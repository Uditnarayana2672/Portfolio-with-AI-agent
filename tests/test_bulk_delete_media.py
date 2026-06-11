import datetime
import uuid
from unittest.mock import Mock, call

from app.api.v1.schemas.media import BulkDeleteMediaResponse
from app.application.dtos.media import BulkDeleteMediaCommand
from app.application.interfaces.image_storage import StorageError
from app.application.use_cases.media.bulk_delete_media import BulkDeleteMedia
from app.application.use_cases.media.delete_media import DeleteMedia
from app.domain.entities.media_asset import MediaAsset
from app.domain.repositories.media_asset_repository import (
    MediaAssetListItem,
    MediaUsageRef,
)


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


def _use_case(repo: Mock, activity: Mock, storage: Mock) -> BulkDeleteMedia:
    return BulkDeleteMedia(
        delete_media=DeleteMedia(repo=repo, activity=activity, storage=storage)
    )


def test_bulk_delete_reports_partial_success_and_freed_bytes() -> None:
    repo = Mock()
    activity = Mock()
    storage = Mock()
    project_id = uuid.uuid4()
    deletable = _asset(
        public_id="portfolio/deletable",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        file_size=512,
    )
    in_use = _asset(
        public_id="portfolio/in-use",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        file_size=1024,
    )
    youtube = _asset()
    missing_id = uuid.uuid4()
    assets = {asset.id: asset for asset in (deletable, in_use, youtube)}
    repo.get.side_effect = lambda asset_id: (
        MediaAssetListItem(asset=assets[asset_id], uploaded_by_name=None)
        if asset_id in assets
        else None
    )
    repo.find_usage.side_effect = lambda public_id: (
        [
            MediaUsageRef(
                kind="project",
                entity_id=project_id,
                title="Lighthouse Analytics",
                location="thumbnail",
            )
        ]
        if public_id == in_use.public_id
        else []
    )

    result = _use_case(repo, activity, storage).execute(
        BulkDeleteMediaCommand(
            asset_ids=[deletable.id, in_use.id, youtube.id, missing_id, deletable.id]
        )
    )

    assert result.deleted == [deletable.id, youtube.id]
    assert result.deleted_count == 2
    assert result.freed_bytes == 512
    assert [(item.id, item.reason) for item in result.skipped] == [
        (in_use.id, "MEDIA_IN_USE"),
        (missing_id, "MEDIA_NOT_FOUND"),
    ]
    assert result.skipped[0].usage_count == 1
    assert result.skipped[0].references[0].title == "Lighthouse Analytics"
    assert result.skipped[1].usage_count == 0
    assert result.skipped[1].references == []
    storage.delete.assert_called_once_with("portfolio/deletable")
    assert repo.delete.call_args_list == [call(deletable.id), call(youtube.id)]
    assert activity.record.call_count == 2

    payload = BulkDeleteMediaResponse.model_validate(result, from_attributes=True)
    assert payload.deleted_count == 2
    assert payload.skipped[0].references[0].model_dump() == {
        "kind": "project",
        "title": "Lighthouse Analytics",
    }


def test_bulk_delete_force_removes_in_use_asset() -> None:
    repo = Mock()
    activity = Mock()
    storage = Mock()
    asset = _asset(
        public_id="portfolio/in-use",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        file_size=1024,
    )
    repo.get.return_value = MediaAssetListItem(asset=asset, uploaded_by_name=None)

    result = _use_case(repo, activity, storage).execute(
        BulkDeleteMediaCommand(asset_ids=[asset.id], force=True)
    )

    assert result.deleted == [asset.id]
    assert result.skipped == []
    assert result.deleted_count == 1
    assert result.freed_bytes == 1024
    repo.find_usage.assert_not_called()
    storage.delete.assert_called_once_with("portfolio/in-use")
    repo.delete.assert_called_once_with(asset.id)


def test_bulk_delete_skips_storage_failure_and_continues() -> None:
    repo = Mock()
    activity = Mock()
    storage = Mock()
    failed = _asset(
        public_id="portfolio/failed",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        file_size=1024,
    )
    deletable = _asset(
        public_id="portfolio/deletable",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        file_size=512,
    )
    assets = {asset.id: asset for asset in (failed, deletable)}
    repo.get.side_effect = lambda asset_id: MediaAssetListItem(
        asset=assets[asset_id], uploaded_by_name=None
    )
    repo.find_usage.return_value = []
    storage.delete.side_effect = [StorageError("provider unavailable"), {}]

    result = _use_case(repo, activity, storage).execute(
        BulkDeleteMediaCommand(asset_ids=[failed.id, deletable.id])
    )

    assert result.deleted == [deletable.id]
    assert [(item.id, item.reason) for item in result.skipped] == [
        (failed.id, "STORAGE_ERROR")
    ]
    assert result.deleted_count == 1
    assert result.freed_bytes == 512
    repo.delete.assert_called_once_with(deletable.id)
    activity.record.assert_called_once()


def test_bulk_delete_route_is_registered(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "false")
    from app.api.v1.endpoints.media import router

    routes = [(route.path, route.methods) for route in router.routes]

    assert ("/admin/media/bulk-delete", {"POST"}) in routes

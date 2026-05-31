import datetime
import uuid
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.api.v1.schemas.media import BulkUpdateMediaResponse
from app.application.dtos.media import BulkUpdateMediaCommand
from app.application.use_cases.media.bulk_update_media import BulkUpdateMedia
from app.application.use_cases.media.update_media import UpdateMedia
from app.domain.entities.media_asset import MediaAsset
from app.domain.exceptions import NotFoundError, ValidationError
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


class FakeMediaRepository:
    def __init__(self, assets: list[MediaAsset]) -> None:
        self.assets = {asset.id: asset for asset in assets}
        self.updates = []

    def get(self, asset_id: uuid.UUID) -> MediaAssetListItem | None:
        asset = self.assets.get(asset_id)
        if asset is None:
            return None
        return MediaAssetListItem(asset=asset, uploaded_by_name=None)

    def public_id_exists(self, public_id: str) -> bool:
        return any(asset.public_id == public_id for asset in self.assets.values())

    def update(self, asset_id: uuid.UUID, changes: dict) -> MediaAssetListItem | None:
        asset = self.assets.get(asset_id)
        if asset is None:
            return None
        self.updates.append((asset_id, changes))
        self.assets[asset_id] = replace(asset, **changes)
        return self.get(asset_id)


def _use_case(repo: FakeMediaRepository, storage: Mock) -> BulkUpdateMedia:
    return BulkUpdateMedia(
        repo=repo,
        update_media=UpdateMedia(repo=repo, storage=storage),
    )


def test_bulk_move_updates_cloudinary_and_youtube_assets_with_collision() -> None:
    storage = Mock()
    existing = _asset(
        public_id="blog/covers/cover",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        format="jpg",
        file_name="cover.jpg",
        folder="blog/covers",
    )
    cloudinary = _asset(
        cloudinary_url="https://res.cloudinary.com/demo/image/upload/projects/cover.jpg",
        public_id="projects/cover",
        resource_type="image",
        source_type="cloudinary",
        external_id=None,
        thumbnail_url=None,
        format="jpg",
        file_name="cover.jpg",
        folder="projects",
    )
    youtube = _asset()
    repo = FakeMediaRepository([existing, cloudinary, youtube])
    storage.rename.return_value = {
        "public_id": "blog/covers/cover-2",
        "secure_url": "https://res.cloudinary.com/demo/image/upload/blog/covers/cover-2.jpg",
    }

    result = _use_case(repo, storage).execute(
        BulkUpdateMediaCommand(
            asset_ids=[cloudinary.id, youtube.id],
            folder="blog/covers",
        )
    )

    assert result.updated_count == 2
    assert [(item.id, item.rename_note) for item in result.renamed] == [
        (
            cloudinary.id,
            "Renamed to cover-2 to avoid collision in blog/covers",
        )
    ]
    assert [asset.folder for asset in result.assets] == ["blog/covers", "blog/covers"]
    assert result.assets[0].file_name == "cover-2.jpg"
    storage.rename.assert_called_once_with(
        "projects/cover",
        "blog/covers/cover-2",
        resource_type="image",
    )

    payload = BulkUpdateMediaResponse.model_validate(result, from_attributes=True)
    assert payload.updated_count == 2
    assert payload.renamed[0].id == cloudinary.id


def test_bulk_alt_text_clear_updates_each_unique_asset_without_cdn_rename() -> None:
    storage = Mock()
    first = _asset(alt_text="Old text")
    second = _asset(alt_text="Other text", external_id="M7lc1UVf-VE")
    repo = FakeMediaRepository([first, second])

    result = _use_case(repo, storage).execute(
        BulkUpdateMediaCommand(
            asset_ids=[first.id, first.id, second.id],
            alt_text=None,
        )
    )

    assert result.updated_count == 2
    assert result.renamed == []
    assert [asset.alt_text for asset in result.assets] == [None, None]
    assert len(repo.updates) == 2
    storage.rename.assert_not_called()


def test_bulk_update_validates_before_mutating_assets() -> None:
    storage = Mock()
    asset = _asset()
    repo = FakeMediaRepository([asset])
    use_case = _use_case(repo, storage)

    with pytest.raises(ValidationError):
        use_case.execute(BulkUpdateMediaCommand(asset_ids=[asset.id]))

    with pytest.raises(ValidationError):
        use_case.execute(
            BulkUpdateMediaCommand(asset_ids=[asset.id], folder="bad folder")
        )

    assert repo.updates == []
    storage.rename.assert_not_called()


def test_bulk_update_preflights_missing_ids_before_mutating_assets() -> None:
    storage = Mock()
    asset = _asset()
    repo = FakeMediaRepository([asset])

    with pytest.raises(NotFoundError):
        _use_case(repo, storage).execute(
            BulkUpdateMediaCommand(
                asset_ids=[asset.id, uuid.uuid4()],
                folder="blog/covers",
            )
        )

    assert repo.updates == []
    storage.rename.assert_not_called()


def test_bulk_update_route_is_registered(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "false")
    from app.api.v1.endpoints.media import router

    routes = [(route.path, route.methods) for route in router.routes]

    assert ("/admin/media/bulk-update", {"POST"}) in routes

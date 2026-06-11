"""Bulk-update selected media assets through the existing single-update policy."""
from __future__ import annotations

from app.application.dtos.media import (
    UNSET,
    BulkUpdateMediaCommand,
    BulkUpdateMediaResult,
    BulkUpdateRenamedItem,
    UpdateMediaCommand,
)
from app.application.use_cases.media.update_media import UpdateMedia, normalize_folder
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.repositories.media_asset_repository import MediaAssetRepository


class BulkUpdateMedia:
    """Apply one shared edit while preserving single-asset update semantics."""

    def __init__(
        self,
        *,
        repo: MediaAssetRepository,
        update_media: UpdateMedia,
    ) -> None:
        self._repo = repo
        self._update_media = update_media

    def execute(self, cmd: BulkUpdateMediaCommand) -> BulkUpdateMediaResult:
        if cmd.folder is UNSET and cmd.alt_text is UNSET:
            raise ValidationError("Provide folder and/or alt_text")

        folder = cmd.folder
        if folder is not UNSET:
            if not isinstance(folder, str):
                raise ValidationError("folder must be a string")
            folder = normalize_folder(folder)

        asset_ids = list(dict.fromkeys(cmd.asset_ids))
        for asset_id in asset_ids:
            if self._repo.get(asset_id) is None:
                raise NotFoundError(f"No media asset with id {asset_id}")

        assets = []
        renamed = []
        for asset_id in asset_ids:
            result = self._update_media.execute(
                UpdateMediaCommand(
                    asset_id=asset_id,
                    folder=folder,
                    alt_text=cmd.alt_text,
                )
            )
            assets.append(result.asset)
            if result.renamed and result.rename_note is not None:
                renamed.append(
                    BulkUpdateRenamedItem(
                        id=asset_id,
                        rename_note=result.rename_note,
                    )
                )

        return BulkUpdateMediaResult(
            updated_count=len(assets),
            renamed=renamed,
            assets=assets,
        )

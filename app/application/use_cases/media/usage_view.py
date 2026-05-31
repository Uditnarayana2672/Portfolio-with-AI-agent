"""Shared mapper: MediaUsageRef → UsageReferenceView (application layer).

Both the /usage endpoint and the delete-in-use guard must present the same
reference shape (with an admin deep link), so the mapping lives in one place.
"""
from __future__ import annotations

from app.application.dtos.media import UsageReferenceView
from app.domain.repositories.media_asset_repository import MediaUsageRef


def to_usage_reference_view(ref: MediaUsageRef) -> UsageReferenceView:
    # 'project' → projects admin; 'blog'/'og' both live under a blog post.
    base = "/admin/projects" if ref.kind == "project" else "/admin/blogs"
    return UsageReferenceView(
        kind=ref.kind,
        id=str(ref.entity_id),
        title=ref.title,
        location=ref.location,
        url=f"{base}/{ref.entity_id}",
    )

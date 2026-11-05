"""Portfolio content document upgrades (domain layer).

The stored document is brought to the current shape on read, so old rows keep
working and the next save persists the new shape.
"""
from __future__ import annotations

import copy

PROJECT_COUNT_SOURCE = "published_projects"


def upgrade_document(content: dict) -> dict:
    """Current shape: no "currently building" card, a portrait slot, and every
    stat naming its source. The student-conversations stat becomes the live
    project count."""
    doc = copy.deepcopy(content)
    hero = doc.get("hero") or {}
    hero.pop("currently_building", None)
    hero.setdefault("portrait", None)
    for stat in (doc.get("about") or {}).get("stats") or []:
        if "source" in stat:
            continue
        if "student conversations" in (stat.get("label") or "").lower():
            stat.update(source=PROJECT_COUNT_SOURCE, value=None, suffix="+", label="scalable projects")
        else:
            stat["source"] = "manual"
    return doc


def resolve_stats(content: dict, published_projects: int) -> dict:
    """Public view: fill automatic stats in with their real values."""
    doc = copy.deepcopy(content)
    for stat in (doc.get("about") or {}).get("stats") or []:
        if stat.get("source") == PROJECT_COUNT_SOURCE:
            stat["value"] = str(published_projects)
    return doc

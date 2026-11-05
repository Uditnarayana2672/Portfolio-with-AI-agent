"""Before-publish checklist (domain layer).

One rule list, used by GET checklist, every save response, preview, publish,
schedule and the scheduler. Blockers stop publishing; warnings never do.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TITLE_RANGE = (10, 100)
EXCERPT_MAX = 200
EXCERPT_IDEAL_MIN = 80
MIN_WORDS = 50
META_TITLE_RANGE = (30, 60)
META_DESCRIPTION_RANGE = (120, 160)


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    label: str
    level: str               # 'blocker' | 'warning'
    passed: bool
    message: str | None = None
    paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Checklist:
    items: list[ChecklistItem]

    @property
    def can_publish(self) -> bool:
        return all(i.passed for i in self.items if i.level == "blocker")

    @property
    def blocker_count(self) -> int:
        return sum(1 for i in self.items if i.level == "blocker" and not i.passed)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.items if i.level == "warning" and not i.passed)

    def first_failure(self) -> ChecklistItem | None:
        return next((i for i in self.items if i.level == "blocker" and not i.passed), None)


@dataclass(frozen=True)
class ChecklistInput:
    title: str
    slug_problem: str | None          # None when the slug is usable
    category_ok: bool
    excerpt: str | None
    word_count: int
    images_missing_alt: list[str]
    missing_media: list[str]          # descriptions of assets that no longer exist
    empty_blocks: list[str]
    heading_order_ok: bool
    has_cover: bool
    has_og: bool
    tag_count: int
    meta_title: str                   # effective (after fallback)
    meta_description: str             # effective (after fallback)


def evaluate(ci: ChecklistInput) -> Checklist:
    title_len = len(ci.title.strip())
    excerpt = (ci.excerpt or "").strip()
    items = [
        ChecklistItem(
            "title", "Title", "blocker",
            TITLE_RANGE[0] <= title_len <= TITLE_RANGE[1],
            None if TITLE_RANGE[0] <= title_len <= TITLE_RANGE[1]
            else f"Title is {title_len} chars; needs {TITLE_RANGE[0]}–{TITLE_RANGE[1]}.",
        ),
        ChecklistItem(
            "slug", "URL slug available", "blocker", ci.slug_problem is None,
            None if ci.slug_problem is None else f"Slug problem: {ci.slug_problem}.",
        ),
        ChecklistItem(
            "category", "Category set", "blocker", ci.category_ok,
            None if ci.category_ok else "Pick a category.",
        ),
        ChecklistItem(
            "excerpt", "Excerpt written", "blocker",
            bool(excerpt) and len(excerpt) <= EXCERPT_MAX,
            None if excerpt and len(excerpt) <= EXCERPT_MAX
            else ("Write a short excerpt for cards and search." if not excerpt
                  else f"Excerpt is {len(excerpt)} chars; max {EXCERPT_MAX}."),
        ),
        ChecklistItem(
            "body", f"At least {MIN_WORDS} words", "blocker", ci.word_count >= MIN_WORDS,
            None if ci.word_count >= MIN_WORDS else f"Body has {ci.word_count} words.",
        ),
        ChecklistItem(
            "image_alt", "Every image has alt text", "blocker", not ci.images_missing_alt,
            None if not ci.images_missing_alt
            else f"{len(ci.images_missing_alt)} image(s) missing alt text.",
            list(ci.images_missing_alt),
        ),
        ChecklistItem(
            "media_exists", "All media still exists", "blocker", not ci.missing_media,
            None if not ci.missing_media else f"Missing: {', '.join(ci.missing_media)}.",
        ),
        ChecklistItem(
            "empty_blocks", "No empty blocks", "warning", not ci.empty_blocks,
            None if not ci.empty_blocks else f"{len(ci.empty_blocks)} empty heading/code/table block(s).",
            list(ci.empty_blocks),
        ),
        ChecklistItem(
            "cover", "Cover image", "warning", ci.has_cover,
            None if ci.has_cover else "Posts without a cover get a plain card.",
        ),
        ChecklistItem(
            "og_image", "Social share image", "warning", ci.has_og or ci.has_cover,
            None if ci.has_og else ("Using the cover image." if ci.has_cover else "No image for social cards."),
        ),
        ChecklistItem(
            "tags", "At least one tag", "warning", ci.tag_count >= 1,
            None if ci.tag_count else "Tags help related posts and tag pages.",
        ),
        ChecklistItem(
            "excerpt_length", "Excerpt 80–200 chars", "warning",
            EXCERPT_IDEAL_MIN <= len(excerpt) <= EXCERPT_MAX,
            None if EXCERPT_IDEAL_MIN <= len(excerpt) <= EXCERPT_MAX else f"Excerpt is {len(excerpt)} chars.",
        ),
        _range_item("meta_title_length", "Meta title 30–60 chars", ci.meta_title, META_TITLE_RANGE),
        _range_item("meta_description_length", "Meta description 120–160 chars",
                    ci.meta_description, META_DESCRIPTION_RANGE),
        ChecklistItem(
            "heading_order", "Headings start at H2", "warning", ci.heading_order_ok,
            None if ci.heading_order_ok else "The first heading is a sub-heading.",
        ),
    ]
    return Checklist(items)


def _range_item(key: str, label: str, value: str, bounds: tuple[int, int]) -> ChecklistItem:
    n = len(value or "")
    ok = bounds[0] <= n <= bounds[1]
    return ChecklistItem(key, label, "warning", ok, None if ok else f"{n} chars.")

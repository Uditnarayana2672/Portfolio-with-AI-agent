"""Per-type config schemas for project content blocks (presentation layer).

Each of the 13 supported block types has its own Pydantic model describing the
shape of its ``config`` object. The Add Block endpoint looks the model up in
``BLOCK_CONFIG_MODELS`` by ``block_type`` and validates the raw config dict
against it before anything reaches the use case.

Validation split:
  - shape (required fields, types, defaults)        → here, via Pydantic
  - business caps (poll 2–6 options, code ≤ 50 000) → AddBlock use case,
    so the rules live with the application logic and raise domain errors
    with the exact documented messages.

Unknown extra fields are ignored (Pydantic's default), per the API contract.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HeroConfig(BaseModel):
    heading: str = Field(..., min_length=1)
    subheading: str | None = None
    background_image_url: str | None = None
    background_color: str | None = None
    overlay_opacity: float = Field(0.5, ge=0.0, le=1.0)
    align: Literal["left", "center", "right"] = "center"
    cta_label: str | None = None
    cta_url: str | None = None
    cta_secondary_label: str | None = None
    cta_secondary_url: str | None = None
    min_height: str | None = None


class TextConfig(BaseModel):
    content: str
    max_width: str = "default"


class ImageConfig(BaseModel):
    image_url: str = Field(..., min_length=1)
    alt_text: str | None = None
    caption: str | None = None
    width: str = "medium"
    align: Literal["left", "center", "right"] = "center"
    link_url: str | None = None
    rounded: bool = False


class GalleryImage(BaseModel):
    url: str = Field(..., min_length=1)
    alt: str | None = None
    caption: str | None = None


class GalleryConfig(BaseModel):
    # An empty gallery is a valid starting state; images are added later.
    images: list[GalleryImage] = Field(default_factory=list)
    layout: str = "grid"
    columns: int = Field(3, ge=1, le=6)
    gap: str = "md"
    show_captions: bool = True


class VideoConfig(BaseModel):
    video_url: str = Field(..., min_length=1)
    provider: str | None = None
    thumbnail_url: str | None = None
    caption: str | None = None
    autoplay: bool = False
    muted: bool = False
    loop: bool = False
    controls: bool = True
    width: str = "full"


class CodeConfig(BaseModel):
    code: str
    language: str = "plaintext"
    filename: str | None = None
    show_line_numbers: bool = True
    highlight_lines: list[int] = Field(default_factory=list)
    theme: str = "dark"


class TimelineItem(BaseModel):
    date: str
    title: str
    description: str | None = None
    icon: str | None = None
    color: str | None = None


class TimelineConfig(BaseModel):
    items: list[TimelineItem] = Field(default_factory=list)
    direction: Literal["vertical", "horizontal"] = "vertical"
    show_connectors: bool = True


class StatMetric(BaseModel):
    value: str
    label: str
    unit: str | None = None
    icon: str | None = None
    color: str | None = None


class StatsConfig(BaseModel):
    metrics: list[StatMetric]
    columns: int = Field(3, ge=1, le=6)
    style: str = "card"


class PollConfig(BaseModel):
    question: str = Field(..., min_length=1)
    # Option count limits (2–6) are enforced by the AddBlock use case.
    options: list[str]
    anonymous: bool = True
    show_results: bool = True
    expiry_date: str | None = None


class QuoteConfig(BaseModel):
    text: str = Field(..., min_length=1)
    attribution_name: str | None = None
    attribution_role: str | None = None
    style: str = "pullquote"
    source_url: str | None = None


class ComparisonConfig(BaseModel):
    left_label: str
    left_content: str
    right_label: str
    right_content: str
    style: str = "split"


class CtaConfig(BaseModel):
    heading: str = Field(..., min_length=1)
    description: str | None = None
    primary_label: str | None = None
    primary_url: str | None = None
    secondary_label: str | None = None
    secondary_url: str | None = None
    background_color: str | None = None
    background_image_url: str | None = None
    align: Literal["left", "center", "right"] = "center"
    style: str = "filled"


class FormConfig(BaseModel):
    form_id: str = Field(..., min_length=1)
    form_name: str | None = None
    embed_type: str = "typeform"
    height: int = Field(480, ge=1)


# The builder always sends the canonical type name (e.g. "stats", never
# "metrics"); anything not in this map is rejected with 422.
BLOCK_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "hero": HeroConfig,
    "text": TextConfig,
    "image": ImageConfig,
    "gallery": GalleryConfig,
    "video": VideoConfig,
    "code": CodeConfig,
    "timeline": TimelineConfig,
    "stats": StatsConfig,
    "poll": PollConfig,
    "quote": QuoteConfig,
    "comparison": ComparisonConfig,
    "cta": CtaConfig,
    "form": FormConfig,
}

"""HTTP schemas and content rules for the portfolio document (presentation layer).

``PortfolioDocument`` is the validation contract for a save. Text is stored and
served as plain text; ``*word*`` only marks highlighted words for the renderer.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.api.v1.schemas.blog import UtcDatetime

MAX_DOCUMENT_BYTES = 64 * 1024

Headline = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptionalLine = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Paragraph = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
ItemId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
Year = Annotated[int, Field(ge=1950, le=2100)]

_LOGO_SLUG = re.compile(r"^[a-z0-9-]{1,60}$")
_SAFE_URL = re.compile(r"^(https://\S+|/\S*)$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique_ids(items: list[Any]) -> list[Any]:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("ids must be unique within the list")
    return items


class Portrait(_Strict):
    url: str
    alt: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    media_asset_id: str | None = None

    @field_validator("url")
    @classmethod
    def _safe_url(cls, value: str) -> str:
        if len(value) > 500 or not _SAFE_URL.match(value):
            raise ValueError("must be an https:// URL or a site path")
        return value


class Hero(_Strict):
    eyebrow: Line
    headline: Headline
    headline_accent: Headline
    intro: Paragraph
    highlights: Annotated[list[Line], Field(max_length=6)]
    portrait: Portrait | None = None


class Stat(_Strict):
    id: ItemId
    source: Literal["manual", "published_projects"] = "manual"
    value: Annotated[str, StringConstraints(strip_whitespace=True, max_length=12)] | None = None
    suffix: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4)]
    label: Line

    @model_validator(mode="after")
    def _value_matches_source(self) -> "Stat":
        if self.source == "manual" and not self.value:
            raise ValueError("a manual stat needs a value")
        if self.source != "manual":
            self.value = None  # always calculated
        return self


class About(_Strict):
    statement: Paragraph
    today: Paragraph
    stats: Annotated[list[Stat], Field(max_length=6)]

    _unique = field_validator("stats")(_unique_ids)


class Point(_Strict):
    id: ItemId
    text: Paragraph


class WhatIDo(_Strict):
    title: Headline
    subtitle: Line
    points: Annotated[list[Point], Field(max_length=8)]

    _unique = field_validator("points")(_unique_ids)


class SectionText(_Strict):
    title: Headline
    title_soft: Headline
    intro: Paragraph


class Tech(_Strict):
    id: ItemId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    logo_slug: str | None = None
    categories: Annotated[list[Literal["ai", "backend", "frontend", "cloud"]], Field(min_length=1, max_length=4)]
    level: Literal["working", "advanced", "expert"]
    show_in_strip: bool
    show_in_what_i_do: bool
    show_in_skills: bool

    @field_validator("logo_slug")
    @classmethod
    def _slug(cls, value: str | None) -> str | None:
        if value is not None and not _LOGO_SLUG.match(value):
            raise ValueError("may only contain lowercase letters, numbers and hyphens")
        return value


class Job(_Strict):
    id: ItemId
    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    start_year: Year
    end_year: Year | None = None
    summary: Paragraph
    highlights: Annotated[list[Line], Field(max_length=8)]

    @model_validator(mode="after")
    def _years(self) -> "Job":
        if self.end_year is not None and self.end_year < self.start_year:
            raise ValueError("end_year cannot be before start_year")
        return self


class PortfolioDocument(_Strict):
    hero: Hero
    about: About
    what_i_do: WhatIDo
    skills: SectionText
    tech: Annotated[list[Tech], Field(max_length=60)]
    experience_section: SectionText
    experience: Annotated[list[Job], Field(max_length=20)]

    _unique = field_validator("tech", "experience")(_unique_ids)


class UpdatePortfolioContentRequest(BaseModel):
    version: int = Field(ge=1)
    content: dict[str, Any]


class AdminPortfolioContentResponse(BaseModel):
    version: int
    updated_at: UtcDatetime
    updated_by_name: str | None
    content: dict[str, Any]


class SavedPortfolioContentResponse(AdminPortfolioContentResponse):
    changed_sections: list[str]


class PublicPortfolioContentResponse(BaseModel):
    updated_at: UtcDatetime
    content: dict[str, Any]

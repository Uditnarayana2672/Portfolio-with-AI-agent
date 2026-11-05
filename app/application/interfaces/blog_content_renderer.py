"""BlogContentRenderer port (application layer).

Turns a validated TipTap document into the HTML readers see, plus the plain
text, table of contents and stats derived from it. Implemented in
infrastructure/rendering.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TocEntry:
    id: str
    text: str
    level: int
    number: str | None


@dataclass(frozen=True)
class RenderedContent:
    html: str
    text: str
    toc: list[TocEntry] = field(default_factory=list)
    word_count: int = 0
    block_count: int = 0
    image_count: int = 0


# Maps a link's ``internal`` ref ({type, id}) to its current URL, or None to keep
# the stored href. Lets internal links survive a target's slug change.
LinkResolver = Callable[[dict], str | None]


class BlogContentRenderer(ABC):
    @abstractmethod
    def render(self, doc: dict, *, link_resolver: LinkResolver | None = None) -> RenderedContent:
        """Render an already-normalized document. Never raises on valid input."""

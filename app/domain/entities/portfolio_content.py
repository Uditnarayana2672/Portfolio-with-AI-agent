"""PortfolioContent domain entity (core layer).

The main portfolio page's editable text, stored as one JSON document. Plain
Python only: no SQLAlchemy, FastAPI or third-party types.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioContent:
    content: dict
    version: int
    updated_at: datetime.datetime
    updated_by_name: str | None

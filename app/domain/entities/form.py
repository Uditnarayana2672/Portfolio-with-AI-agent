"""Form domain entity (core layer).

Framework-free representation of a form definition. No SQLAlchemy, FastAPI,
or third-party types here — just plain Python.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Form:
    id: uuid.UUID
    author_id: uuid.UUID
    name: str
    form_type: str   # 'contact' | 'discovery' | 'feedback' | 'waitlist' | 'custom'
    config: dict
    created_at: datetime.datetime
    updated_at: datetime.datetime

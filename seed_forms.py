#!/usr/bin/env python
"""Seed the forms table with the 5 mock forms used by the frontend.

Usage:
    DATABASE_URL=postgresql://... python seed_forms.py

Idempotent: exits early if forms already exist for the admin user.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required.", file=sys.stderr)
    sys.exit(1)

FORMS = [
    {"name": "Contact / general enquiry", "form_type": "contact"},
    {"name": "Project discovery call request", "form_type": "discovery"},
    {"name": "Jerry intake questionnaire", "form_type": "custom"},
    {"name": "Bug report form", "form_type": "feedback"},
    {"name": "Beta access waitlist", "form_type": "waitlist"},
]

engine = create_engine(DATABASE_URL)

with Session(engine) as session:
    row = session.execute(
        text("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1")
    ).first()

    if not row:
        print("ERROR: No admin user found. Create one first.", file=sys.stderr)
        sys.exit(1)

    author_id = row[0]

    existing = session.execute(
        text("SELECT COUNT(*) FROM forms WHERE author_id = :author_id"),
        {"author_id": str(author_id)},
    ).scalar()

    if existing:
        print(f"Forms already seeded ({existing} existing for admin {author_id}). Skipping.")
        sys.exit(0)

    for form in FORMS:
        session.execute(
            text(
                "INSERT INTO forms (name, form_type, author_id, config) "
                "VALUES (:name, :form_type, :author_id, '{}'::jsonb)"
            ),
            {"name": form["name"], "form_type": form["form_type"], "author_id": str(author_id)},
        )

    session.commit()
    print(f"Seeded {len(FORMS)} forms for admin {author_id}.")

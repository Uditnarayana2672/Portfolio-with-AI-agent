"""The example env file is public, so it must never hold real values."""
from __future__ import annotations

from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
SECRET_NAMES = ("DATABASE_URL", "DIRECT_URL", "SECRET", "API_KEY", "ANON_KEY", "DEPLOY_HOOK", "PASSWORD", "TOKEN")
PLACEHOLDER_MARKS = ("<", "your", "example", "placeholder", "changeme", "xxx")


def test_env_example_has_no_real_secrets():
    offenders = []
    for raw in EXAMPLE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        is_secret_name = any(part in name.upper() for part in SECRET_NAMES)
        if is_secret_name and value and not any(mark in value.lower() for mark in PLACEHOLDER_MARKS):
            offenders.append(name.strip())  # names only: never print the value
    assert offenders == [], f"Replace these with placeholders in .env.example: {offenders}"

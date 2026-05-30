"""Project-wide configuration constants for the automation workflow."""

from __future__ import annotations

import os


def get_optional_env(name: str, default: str | None = None) -> str | None:
    """Read an optional environment variable without logging its value."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def get_required_env(name: str) -> str:
    """Read a required environment variable without exposing its value."""
    value = get_optional_env(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_optional_int(name: str, default: int) -> int:
    value = get_optional_env(name)
    if value is None:
        return default
    return int(value)


STEPHEN_EMAIL: str = get_optional_env("STEPHEN_EMAIL", "7173783020@hellofax.com") or "7173783020@hellofax.com"
GMAIL_ACCOUNT: str = get_optional_env("GMAIL_ACCOUNT", "bettercrafterorders@gmail.com") or "bettercrafterorders@gmail.com"
FIRESTORE_COLLECTION: str = get_optional_env("FIRESTORE_COLLECTION", "processed_emails") or "processed_emails"
STORAGE_BUCKET: str | None = get_optional_env("STORAGE_BUCKET")
SEARCH_HOURS_BACK: int = _get_optional_int("SEARCH_HOURS_BACK", 12)

GMAIL_READONLY_SCOPE: str = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_TOKEN_URI: str = "https://oauth2.googleapis.com/token"

GMAIL_CLIENT_ID: str | None = get_optional_env("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET: str | None = get_optional_env("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN: str | None = get_optional_env("GMAIL_REFRESH_TOKEN")
GOOGLE_CREDENTIALS_JSON: str | None = get_optional_env("GOOGLE_CREDENTIALS_JSON")
GEMINI_API_KEY: str | None = get_optional_env("GEMINI_API_KEY")

REPORT_PREFIX: str = get_optional_env("REPORT_PREFIX", "reports/stephen") or "reports/stephen"
TEMPLATE_PATH: str = get_optional_env("TEMPLATE_PATH", "templates/stephen_template.docx") or "templates/stephen_template.docx"

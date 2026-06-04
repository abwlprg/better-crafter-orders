"""Presence-only configuration diagnostics for local setup and admin checks."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping, NamedTuple


class ConfigKey(NamedTuple):
    name: str
    category: str
    required: bool


# Current 2.0 diagnostics are presence/status only. Values are never returned.
# Production-later and legacy-reference keys are intentionally optional.
CONFIG_KEYS: tuple[ConfigKey, ...] = (
    ConfigKey("ADMIN_API_KEY", "admin", True),
    ConfigKey("GMAIL_ACCOUNT", "gmail", True),
    ConfigKey("GMAIL_CLIENT_ID", "gmail", True),
    ConfigKey("GMAIL_CLIENT_SECRET", "gmail", True),
    ConfigKey("GMAIL_REFRESH_TOKEN", "gmail", True),
    ConfigKey("MS_CLIENT_ID", "onedrive", True),
    ConfigKey("MS_TENANT_ID", "onedrive", True),
    ConfigKey("MS_REFRESH_TOKEN", "onedrive", True),
    ConfigKey("ONEDRIVE_DRIVE_ID", "onedrive", True),
    ConfigKey("ONEDRIVE_FILE_ID", "onedrive", True),
    ConfigKey("GCP_PROJECT", "local_admin_app", False),
    ConfigKey("ALLOWED_ORIGINS", "local_admin_app", False),
    ConfigKey("ONEDRIVE_TEST_DRIVE_ID", "onedrive_sandbox", False),
    ConfigKey("ONEDRIVE_TEST_FILE_ID", "onedrive_sandbox", False),
    ConfigKey("ONEDRIVE_SANDBOX_WRITE_ENABLED", "onedrive_sandbox", False),
    ConfigKey("GEMINI_API_KEY", "optional_gemini", False),
    ConfigKey("MS_CLIENT_SECRET", "production_later", False),
    ConfigKey("GOOGLE_CREDENTIALS_JSON", "optional", False),
    ConfigKey("CLAUDE_API_KEY", "optional", False),
    ConfigKey("STORAGE_BUCKET", "legacy_reference", False),
    ConfigKey("FIRESTORE_COLLECTION", "legacy_reference", False),
    ConfigKey("SEARCH_HOURS_BACK", "legacy_reference", False),
    ConfigKey("REPORT_PREFIX", "legacy_reference", False),
    ConfigKey("TEMPLATE_PATH", "legacy_reference", False),
)


def _value_status(value: str | None) -> str:
    """Classify config presence without returning the raw value."""
    if not value or not value.strip():
        return "missing"

    normalized = value.strip().lower()
    placeholder_tokens = (
        "placeholder",
        "placeholder_",
        "change_me",
        "changeme",
        "todo",
        "replace_me",
        "set_me",
    )
    if any(normalized == token or normalized.startswith(token) for token in placeholder_tokens):
        return "placeholder"

    return "present"


def load_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Load key presence from a dotenv-style file without printing values."""
    env_path = Path(path)
    if not env_path.exists():
        return {}

    parsed: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        parsed[key.strip()] = raw_value.strip()
    return parsed


def merged_environment(env_file: str | Path = ".env") -> dict[str, str]:
    """Match app-local dotenv behavior: process env wins over .env."""
    merged = dict(os.environ)
    for key, entry in load_env_file(env_file).items():
        merged.setdefault(key, entry)
    return merged


def get_config_diagnostics(env: Mapping[str, str]) -> dict:
    """Return key presence diagnostics without values or derived secret data."""
    keys: dict[str, dict[str, bool | str]] = {}
    missing_required: list[str] = []

    for item in CONFIG_KEYS:
        state = _value_status(env.get(item.name))
        present = state == "present"
        keys[item.name] = {
            "present": present,
            "status": state,
            "required": item.required,
            "category": item.category,
        }
        if item.required and not present:
            missing_required.append(item.name)

    return {
        "status": "missing_required" if missing_required else "ok",
        "keys": keys,
        "missing_required": missing_required,
    }


def main() -> int:
    diagnostics = get_config_diagnostics(merged_environment())
    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 1 if diagnostics["missing_required"] else 0


if __name__ == "__main__":
    sys.exit(main())

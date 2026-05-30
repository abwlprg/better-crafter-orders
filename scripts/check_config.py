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


CONFIG_KEYS: tuple[ConfigKey, ...] = (
    ConfigKey("GMAIL_ACCOUNT", "gmail", True),
    ConfigKey("GMAIL_CLIENT_ID", "gmail", True),
    ConfigKey("GMAIL_CLIENT_SECRET", "gmail", True),
    ConfigKey("GMAIL_REFRESH_TOKEN", "gmail", True),
    ConfigKey("ADMIN_API_KEY", "admin", True),
    ConfigKey("MS_CLIENT_ID", "onedrive", True),
    ConfigKey("MS_TENANT_ID", "onedrive", True),
    ConfigKey("MS_REFRESH_TOKEN", "onedrive", True),
    ConfigKey("ONEDRIVE_DRIVE_ID", "onedrive", True),
    ConfigKey("ONEDRIVE_FILE_ID", "onedrive", True),
    ConfigKey("MS_CLIENT_SECRET", "optional", False),
    ConfigKey("GEMINI_API_KEY", "optional", False),
    ConfigKey("CLAUDE_API_KEY", "optional", False),
    ConfigKey("GCP_PROJECT", "optional", False),
    ConfigKey("ALLOWED_ORIGINS", "optional", False),
    ConfigKey("GOOGLE_CREDENTIALS_JSON", "optional", False),
    ConfigKey("STORAGE_BUCKET", "optional", False),
    ConfigKey("FIRESTORE_COLLECTION", "optional", False),
    ConfigKey("SEARCH_HOURS_BACK", "optional", False),
    ConfigKey("REPORT_PREFIX", "optional", False),
    ConfigKey("TEMPLATE_PATH", "optional", False),
)


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
        present = bool(env.get(item.name, "").strip())
        keys[item.name] = {
            "present": present,
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

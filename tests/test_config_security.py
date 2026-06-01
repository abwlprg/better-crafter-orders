"""Tests for environment-driven config and tracked-source credential hygiene."""

from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from functions import config


class TestConfigEnvironmentHelpers(unittest.TestCase):
    def test_required_env_returns_value_when_present(self) -> None:
        with patch.dict(os.environ, {"UNIT_TEST_REQUIRED_ENV": "configured"}, clear=False):
            self.assertEqual(config.get_required_env("UNIT_TEST_REQUIRED_ENV"), "configured")

    def test_required_env_raises_name_only_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                config.get_required_env("UNIT_TEST_REQUIRED_ENV")

        message = str(ctx.exception)
        self.assertIn("UNIT_TEST_REQUIRED_ENV", message)
        self.assertNotIn("=", message)

    def test_optional_env_returns_default_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                config.get_optional_env("UNIT_TEST_OPTIONAL_ENV", "fallback"),
                "fallback",
            )

    def test_optional_env_strips_empty_values_to_default(self) -> None:
        with patch.dict(os.environ, {"UNIT_TEST_OPTIONAL_ENV": "   "}, clear=True):
            self.assertEqual(
                config.get_optional_env("UNIT_TEST_OPTIONAL_ENV", "fallback"),
                "fallback",
            )


class TestTrackedSourceCredentialHygiene(unittest.TestCase):
    repo_root = Path(__file__).resolve().parents[1]

    def test_env_example_uses_placeholders_for_sensitive_values(self) -> None:
        sensitive_keys = {
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
            "GMAIL_REFRESH_TOKEN",
            "GOOGLE_CREDENTIALS_JSON",
            "MS_CLIENT_ID",
            "MS_CLIENT_SECRET",
            "MS_REFRESH_TOKEN",
            "ONEDRIVE_DRIVE_ID",
            "ONEDRIVE_FILE_ID",
            "ONEDRIVE_TEST_DRIVE_ID",
            "ONEDRIVE_TEST_FILE_ID",
            "GEMINI_API_KEY",
            "ADMIN_API_KEY",
        }
        values = {}
        for line in (self.repo_root / ".env.example").read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value

        for key in sensitive_keys:
            self.assertIn(key, values)
            value = values[key].strip()
            self.assertTrue(
                not value or "placeholder" in value,
                f"{key} must be empty or use a placeholder value",
            )

    def test_tracked_source_has_no_known_live_credential_literals(self) -> None:
        tracked = subprocess.check_output(
            ["git", "ls-files"],
            cwd=self.repo_root,
            text=True,
        ).splitlines()

        secret_like_patterns = [
            re.compile("AI" + "za" + r"[0-9A-Za-z_\-]{20,}"),
            re.compile("GO" + "CSPX-" + r"[0-9A-Za-z_\-]+"),
            re.compile("1" + r"//[0-9A-Za-z_\-]+"),
        ]
        suffixes = {".py", ".sh", ".md", ".txt", ".example", ".json", ".js", ".jsx"}

        hits = []
        for rel_path in tracked:
            path = self.repo_root / rel_path
            if path.suffix.lower() not in suffixes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line_number, line in enumerate(text.splitlines(), 1):
                for pattern in secret_like_patterns:
                    if pattern.search(line):
                        hits.append(f"{rel_path}:{line_number}:{pattern.pattern[:2]}...")

        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()

"""Tests for safe configuration diagnostics."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api
from scripts import check_config


REQUIRED_ENV = {
    "GMAIL_ACCOUNT": "configured-gmail-account",
    "GMAIL_CLIENT_ID": "configured-gmail-client-id",
    "GMAIL_CLIENT_SECRET": "configured-gmail-client-secret",
    "GMAIL_REFRESH_TOKEN": "configured-gmail-refresh-token",
    "ADMIN_API_KEY": "configured-admin-key",
    "MS_CLIENT_ID": "configured-ms-client-id",
    "MS_TENANT_ID": "configured-ms-tenant-id",
    "MS_REFRESH_TOKEN": "configured-ms-refresh-token",
    "ONEDRIVE_DRIVE_ID": "configured-onedrive-drive-id",
    "ONEDRIVE_FILE_ID": "configured-onedrive-file-id",
}


class TestConfigDiagnostics(unittest.TestCase):
    def test_present_required_keys_produce_ok(self) -> None:
        result = check_config.get_config_diagnostics(REQUIRED_ENV)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["missing_required"], [])
        self.assertTrue(result["keys"]["GMAIL_CLIENT_ID"]["present"])

    def test_missing_required_keys_produce_missing_required(self) -> None:
        env = dict(REQUIRED_ENV)
        env.pop("GMAIL_REFRESH_TOKEN")

        result = check_config.get_config_diagnostics(env)

        self.assertEqual(result["status"], "missing_required")
        self.assertEqual(result["missing_required"], ["GMAIL_REFRESH_TOKEN"])
        self.assertFalse(result["keys"]["GMAIL_REFRESH_TOKEN"]["present"])

    def test_output_does_not_include_actual_env_values(self) -> None:
        secret_markers = set(REQUIRED_ENV.values())
        result = check_config.get_config_diagnostics(REQUIRED_ENV)
        serialized = json.dumps(result)

        for marker in secret_markers:
            self.assertNotIn(marker, serialized)

    def test_optional_missing_keys_do_not_fail(self) -> None:
        result = check_config.get_config_diagnostics(REQUIRED_ENV)

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["keys"]["GEMINI_API_KEY"]["present"])
        self.assertFalse(result["keys"]["GEMINI_API_KEY"]["required"])

    def test_categories_and_required_flags_are_included(self) -> None:
        result = check_config.get_config_diagnostics(REQUIRED_ENV)

        self.assertEqual(result["keys"]["GMAIL_CLIENT_ID"]["category"], "gmail")
        self.assertTrue(result["keys"]["GMAIL_CLIENT_ID"]["required"])
        self.assertEqual(result["keys"]["ADMIN_API_KEY"]["category"], "admin")
        self.assertEqual(result["keys"]["MS_REFRESH_TOKEN"]["category"], "onedrive")

    def test_load_env_file_parses_presence_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("GMAIL_CLIENT_ID=configured\n# ignored\nEMPTY=\n", encoding="utf-8")

            result = check_config.load_env_file(env_path)

        self.assertEqual(set(result), {"GMAIL_CLIENT_ID", "EMPTY"})

    def test_cli_main_returns_nonzero_when_required_keys_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "scripts.check_config.load_env_file",
            return_value={},
        ):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                exit_code = check_config.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("missing_required", output.getvalue())

    def test_cli_main_returns_zero_when_required_keys_present(self) -> None:
        with patch.dict(os.environ, REQUIRED_ENV, clear=True), patch(
            "scripts.check_config.load_env_file",
            return_value={},
        ):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                exit_code = check_config.main()

        self.assertEqual(exit_code, 0)
        serialized = output.getvalue()
        self.assertIn('"status": "ok"', serialized)
        for marker in REQUIRED_ENV.values():
            self.assertNotIn(marker, serialized)


class TestConfigDiagnosticsApi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(api.app)

    def test_no_admin_header_rejects_request(self) -> None:
        with patch.dict(os.environ, {"ADMIN_API_KEY": "configured-admin-key"}, clear=False):
            response = self.client.get("/api/config-diagnostics")

        self.assertEqual(response.status_code, 401)

    def test_wrong_admin_header_rejects_request(self) -> None:
        with patch.dict(os.environ, {"ADMIN_API_KEY": "configured-admin-key"}, clear=False):
            response = self.client.get(
                "/api/config-diagnostics",
                headers={"X-Admin-API-Key": "wrong-key"},
            )

        self.assertEqual(response.status_code, 401)

    def test_correct_admin_header_returns_presence_only_diagnostic(self) -> None:
        env = dict(REQUIRED_ENV)
        with patch.dict(os.environ, env, clear=True):
            response = self.client.get(
                "/api/config-diagnostics",
                headers={"X-Admin-API-Key": env["ADMIN_API_KEY"]},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["keys"]["ADMIN_API_KEY"]["present"])
        serialized = json.dumps(data)
        for marker in env.values():
            self.assertNotIn(marker, serialized)

    def test_config_status_reports_gemini_enabled_when_key_present(self) -> None:
        env = dict(REQUIRED_ENV, GEMINI_API_KEY="configured-gemini-key")
        with patch.dict(os.environ, env, clear=True):
            response = self.client.get(
                "/api/config-status",
                headers={"X-Admin-API-Key": env["ADMIN_API_KEY"]},
            )

        self.assertEqual(response.status_code, 200)
        gemini = response.json()["gemini"]
        self.assertTrue(gemini["api_key"])
        self.assertTrue(gemini["enabled"])
        self.assertEqual(gemini["reason"], "billing_confirmed")
        self.assertNotIn(env["GEMINI_API_KEY"], json.dumps(response.json()))


if __name__ == "__main__":
    unittest.main()

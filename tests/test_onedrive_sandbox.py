"""Tests for the local OneDrive sandbox harness."""

from __future__ import annotations

import inspect
import io
import unittest
from unittest.mock import patch

from scripts import test_onedrive_sandbox as harness


def valid_env(**overrides: str) -> dict[str, str]:
    env = {
        "MS_CLIENT_ID": "unit-ms-client-id",
        "MS_TENANT_ID": "unit-ms-tenant-id",
        "MS_REFRESH_TOKEN": "unit-ms-refresh-token",
        "MS_CLIENT_SECRET": "unit-ms-client-secret",
        "ONEDRIVE_DRIVE_ID": "prod-drive-id",
        "ONEDRIVE_FILE_ID": "prod-file-id",
        "ONEDRIVE_TEST_DRIVE_ID": "sandbox-drive-id",
        "ONEDRIVE_TEST_FILE_ID": "sandbox-file-id",
        "ONEDRIVE_SANDBOX_WRITE_ENABLED": "false",
    }
    env.update(overrides)
    return env


class FakeSandboxClient:
    def __init__(
        self,
        metadata: dict | None = None,
        content: bytes = b"original-docx-bytes",
    ) -> None:
        self.metadata = metadata or {
            "name": "SANDBOX COPY Stephen Orders.docx",
            "file": {
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            },
        }
        self.content = content
        self.metadata_calls = 0
        self.download_calls = 0
        self.upload_calls = 0
        self.uploaded_content: bytes | None = None

    def get_metadata(self) -> dict:
        self.metadata_calls += 1
        return self.metadata

    def download_docx(self) -> bytes:
        self.download_calls += 1
        return self.content

    def upload_docx(self, content: bytes) -> None:
        self.upload_calls += 1
        self.uploaded_content = content


class TestOneDriveSandboxConfig(unittest.TestCase):
    def test_missing_test_drive_file_vars_fail_config_check(self) -> None:
        env = valid_env(ONEDRIVE_TEST_DRIVE_ID="", ONEDRIVE_TEST_FILE_ID="")
        output = io.StringIO()

        exit_code = harness.print_config_status(env, output=output)
        status = harness.config_status(env)

        self.assertEqual(exit_code, 1)
        self.assertIn("ONEDRIVE_TEST_DRIVE_ID", status.missing_required)
        self.assertIn("ONEDRIVE_TEST_FILE_ID", status.missing_required)

    def test_present_test_drive_file_vars_pass_config_check(self) -> None:
        output = io.StringIO()

        exit_code = harness.print_config_status(valid_env(), output=output)

        self.assertEqual(exit_code, 0)

    def test_config_check_does_not_print_env_values(self) -> None:
        env = valid_env(
            MS_CLIENT_ID="client-value-that-must-not-print",
            MS_TENANT_ID="tenant-value-that-must-not-print",
            MS_REFRESH_TOKEN="refresh-value-that-must-not-print",
            MS_CLIENT_SECRET="secret-value-that-must-not-print",
            ONEDRIVE_TEST_DRIVE_ID="drive-value-that-must-not-print",
            ONEDRIVE_TEST_FILE_ID="file-value-that-must-not-print",
        )
        output = io.StringIO()

        harness.print_config_status(env, output=output)
        printed = output.getvalue()

        for value in env.values():
            if value in {"false", "true", "prod-drive-id", "prod-file-id"}:
                continue
            self.assertNotIn(value, printed)


class TestOneDriveSandboxWriteSafety(unittest.TestCase):
    def test_write_mode_fails_without_explicit_flag(self) -> None:
        fake_client = FakeSandboxClient()

        with self.assertRaises(harness.SafetyRefusal):
            harness.print_write_test(
                valid_env(ONEDRIVE_SANDBOX_WRITE_ENABLED="false"),
                make_client=lambda _drive_id, _file_id: fake_client,
                output=io.StringIO(),
            )

        self.assertEqual(fake_client.metadata_calls, 0)
        self.assertEqual(fake_client.upload_calls, 0)

    def test_write_mode_fails_if_test_ids_match_production_ids(self) -> None:
        fake_client = FakeSandboxClient()

        with self.assertRaises(harness.SafetyRefusal):
            harness.print_write_test(
                valid_env(
                    ONEDRIVE_SANDBOX_WRITE_ENABLED="true",
                    ONEDRIVE_TEST_DRIVE_ID="prod-drive-id",
                ),
                make_client=lambda _drive_id, _file_id: fake_client,
                output=io.StringIO(),
            )

        self.assertEqual(fake_client.metadata_calls, 0)
        self.assertEqual(fake_client.upload_calls, 0)

    def test_write_mode_fails_if_metadata_name_is_not_sandbox_like(self) -> None:
        fake_client = FakeSandboxClient(metadata={"name": "Stephen Orders.docx"})

        with self.assertRaises(harness.SafetyRefusal):
            harness.print_write_test(
                valid_env(ONEDRIVE_SANDBOX_WRITE_ENABLED="true"),
                make_client=lambda _drive_id, _file_id: fake_client,
                output=io.StringIO(),
            )

        self.assertEqual(fake_client.metadata_calls, 1)
        self.assertEqual(fake_client.download_calls, 0)
        self.assertEqual(fake_client.upload_calls, 0)

    def test_write_mode_uses_mocked_onedrive_client_only(self) -> None:
        fake_client = FakeSandboxClient()
        output = io.StringIO()

        with patch.object(
            harness,
            "append_sandbox_row_to_docx",
            return_value=(b"updated-docx-bytes", 1, 0),
        ):
            exit_code = harness.print_write_test(
                valid_env(ONEDRIVE_SANDBOX_WRITE_ENABLED="true"),
                make_client=lambda _drive_id, _file_id: fake_client,
                output=output,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_client.metadata_calls, 1)
        self.assertEqual(fake_client.download_calls, 1)
        self.assertEqual(fake_client.upload_calls, 1)
        self.assertEqual(fake_client.uploaded_content, b"updated-docx-bytes")
        self.assertIn(harness.SANDBOX_TEST_MARKER, output.getvalue())


class TestOneDriveSandboxMetadata(unittest.TestCase):
    def test_metadata_mode_uses_mocked_microsoft_graph_client_only(self) -> None:
        fake_client = FakeSandboxClient()
        output = io.StringIO()

        exit_code = harness.print_metadata_check(
            valid_env(),
            make_client=lambda _drive_id, _file_id: fake_client,
            output=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_client.metadata_calls, 1)
        self.assertEqual(fake_client.download_calls, 0)
        self.assertEqual(fake_client.upload_calls, 0)
        self.assertIn("Metadata read: succeeded", output.getvalue())


class TestOneDriveSandboxIsolation(unittest.TestCase):
    def test_no_mail_reader_imported_or_called(self) -> None:
        source = inspect.getsource(harness)

        self.assertNotIn("GmailClient", source)
        self.assertNotIn("g" + "mail_client", source)

    def test_no_production_endpoint_is_called(self) -> None:
        source = inspect.getsource(harness)
        forbidden_fragments = (
            "append-to-one" + "drive",
            "daily-" + "update",
            "clear-one" + "drive-rows",
            "renew-g" + "mail-watch",
            "g" + "mail-webhook",
        )

        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, source)


if __name__ == "__main__":
    unittest.main()

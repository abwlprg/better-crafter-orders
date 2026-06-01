"""Local-only OneDrive sandbox test harness.

This script validates Microsoft / OneDrive configuration and can optionally
exercise a cloned sandbox Word document. It never uses production OneDrive
target IDs and does not expose secrets in output.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, TextIO

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from functions import onedrive_client


REQUIRED_ENV_KEYS = (
    "MS_CLIENT_ID",
    "MS_TENANT_ID",
    "MS_REFRESH_TOKEN",
    "ONEDRIVE_TEST_DRIVE_ID",
    "ONEDRIVE_TEST_FILE_ID",
)
OPTIONAL_ENV_KEYS = ("MS_CLIENT_SECRET",)
WRITE_FLAG_KEY = "ONEDRIVE_SANDBOX_WRITE_ENABLED"
PRODUCTION_ID_KEYS = ("ONEDRIVE_DRIVE_ID", "ONEDRIVE_FILE_ID")
SANDBOX_NAME_MARKERS = ("TEST", "SANDBOX", "COPY", "CLONE")
SANDBOX_TEST_MARKER = "SANDBOX TEST - SAFE TO DELETE"


class SafetyRefusal(RuntimeError):
    """Raised when a sandbox safety precondition is not met."""


@dataclass(frozen=True)
class ConfigStatus:
    missing_required: tuple[str, ...]
    present_required: tuple[str, ...]
    present_optional: tuple[str, ...]
    missing_optional: tuple[str, ...]
    write_flag_enabled: bool


class SandboxOneDriveClient:
    """Minimal Graph client pinned to explicit sandbox drive and item IDs."""

    def __init__(self, drive_id: str, file_id: str, session=requests) -> None:
        self._drive_id = drive_id
        self._file_id = file_id
        self._session = session

    def _item_url(self, suffix: str = "") -> str:
        return f"{onedrive_client.GRAPH_BASE}/drives/{self._drive_id}/items/{self._file_id}{suffix}"

    @staticmethod
    def _raise_safe_http_error(response: requests.Response, action: str) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            status = getattr(response, "status_code", "unknown")
            raise RuntimeError(
                f"Microsoft Graph {action} failed with HTTP status {status}"
            ) from error

    def get_metadata(self) -> dict:
        response = self._session.get(
            self._item_url(),
            headers=onedrive_client._headers(),
            timeout=30,
        )
        self._raise_safe_http_error(response, "metadata read")
        return response.json()

    def download_docx(self) -> bytes:
        response = self._session.get(
            self._item_url("/content"),
            headers=onedrive_client._headers(),
            timeout=60,
        )
        self._raise_safe_http_error(response, "sandbox download")
        return response.content

    def upload_docx(self, content: bytes) -> None:
        headers = onedrive_client._headers()
        headers["Content-Type"] = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response = self._session.put(
            self._item_url("/content"),
            headers=headers,
            data=content,
            timeout=120,
        )
        self._raise_safe_http_error(response, "sandbox upload")


def load_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Load dotenv-style values without printing them."""
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
    """Match local app behavior: process env wins over .env."""
    merged = dict(os.environ)
    for key, value in load_env_file(env_file).items():
        merged.setdefault(key, value)
    return merged


def _configured(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return not value.strip().lower().startswith("placeholder_")


def config_status(env: Mapping[str, str]) -> ConfigStatus:
    present_required = tuple(key for key in REQUIRED_ENV_KEYS if _configured(env.get(key)))
    missing_required = tuple(key for key in REQUIRED_ENV_KEYS if key not in present_required)
    present_optional = tuple(key for key in OPTIONAL_ENV_KEYS if _configured(env.get(key)))
    missing_optional = tuple(key for key in OPTIONAL_ENV_KEYS if key not in present_optional)
    write_flag_enabled = env.get(WRITE_FLAG_KEY, "").strip().lower() == "true"

    return ConfigStatus(
        missing_required=missing_required,
        present_required=present_required,
        present_optional=present_optional,
        missing_optional=missing_optional,
        write_flag_enabled=write_flag_enabled,
    )


def print_config_status(env: Mapping[str, str], output: TextIO = sys.stdout) -> int:
    status = config_status(env)

    print("OneDrive sandbox config readiness:", file=output)
    for key in REQUIRED_ENV_KEYS:
        state = "present" if key in status.present_required else "missing"
        print(f"- {key}: {state}", file=output)
    for key in OPTIONAL_ENV_KEYS:
        state = "present" if key in status.present_optional else "missing (optional)"
        print(f"- {key}: {state}", file=output)

    flag_state = "true" if status.write_flag_enabled else "false"
    print(f"- {WRITE_FLAG_KEY}: {flag_state}", file=output)
    print("No Microsoft Graph calls were made.", file=output)

    if status.missing_required:
        print(
            "Missing required sandbox config: "
            + ", ".join(status.missing_required),
            file=output,
        )
        return 1
    return 0


def require_sandbox_ids(env: Mapping[str, str]) -> tuple[str, str]:
    missing = [
        key
        for key in ("ONEDRIVE_TEST_DRIVE_ID", "ONEDRIVE_TEST_FILE_ID")
        if not _configured(env.get(key))
    ]
    if missing:
        raise SafetyRefusal("Missing required sandbox test IDs: " + ", ".join(missing))

    drive_id = env["ONEDRIVE_TEST_DRIVE_ID"].strip()
    file_id = env["ONEDRIVE_TEST_FILE_ID"].strip()
    refuse_if_matches_production_ids(env, drive_id, file_id)
    return drive_id, file_id


def refuse_if_matches_production_ids(
    env: Mapping[str, str], test_drive_id: str, test_file_id: str
) -> None:
    production_drive_id = env.get("ONEDRIVE_DRIVE_ID", "").strip()
    production_file_id = env.get("ONEDRIVE_FILE_ID", "").strip()

    if production_drive_id and test_drive_id == production_drive_id:
        raise SafetyRefusal("Sandbox drive ID matches production ONEDRIVE_DRIVE_ID")
    if production_file_id and test_file_id == production_file_id:
        raise SafetyRefusal("Sandbox file ID matches production ONEDRIVE_FILE_ID")


def require_write_flag(env: Mapping[str, str]) -> None:
    if env.get(WRITE_FLAG_KEY, "").strip().lower() != "true":
        raise SafetyRefusal(f"{WRITE_FLAG_KEY}=true is required for sandbox writes")


def metadata_name_looks_sandbox(name: str | None) -> bool:
    normalized = (name or "").upper()
    return any(marker in normalized for marker in SANDBOX_NAME_MARKERS)


def safe_file_type(metadata: Mapping[str, object]) -> str:
    name = str(metadata.get("name") or "")
    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix:
        return suffix

    file_info = metadata.get("file")
    if isinstance(file_info, Mapping):
        mime_type = str(file_info.get("mimeType") or "").lower()
        if "wordprocessingml.document" in mime_type:
            return "docx"
    return "unknown"


def require_sandbox_metadata(metadata: Mapping[str, object]) -> str:
    name = str(metadata.get("name") or "")
    if not metadata_name_looks_sandbox(name):
        raise SafetyRefusal(
            "Sandbox file name must include TEST, SANDBOX, COPY, or CLONE"
        )

    file_type = safe_file_type(metadata)
    if file_type != "docx":
        raise SafetyRefusal("Sandbox write harness currently supports .docx files only")
    return name


def apply_runtime_environment(env: Mapping[str, str]) -> None:
    """Populate process env for the existing delegated Microsoft auth helper."""
    for key in REQUIRED_ENV_KEYS + OPTIONAL_ENV_KEYS + PRODUCTION_ID_KEYS:
        value = env.get(key)
        if value is not None:
            os.environ.setdefault(key, value)


def client_factory(drive_id: str, file_id: str) -> SandboxOneDriveClient:
    return SandboxOneDriveClient(drive_id, file_id)


def print_metadata_check(
    env: Mapping[str, str],
    make_client: Callable[[str, str], SandboxOneDriveClient] = client_factory,
    output: TextIO = sys.stdout,
) -> int:
    drive_id, file_id = require_sandbox_ids(env)
    apply_runtime_environment(env)
    client = make_client(drive_id, file_id)
    metadata = client.get_metadata()
    name = str(metadata.get("name") or "")
    file_type = safe_file_type(metadata)

    print("OneDrive sandbox metadata check: sandbox/test file only.", file=output)
    print("Metadata read: succeeded", file=output)
    if metadata_name_looks_sandbox(name):
        print(f"Item name: {name}", file=output)
    else:
        print(
            "Item name: not printed because it lacks a sandbox/test marker",
            file=output,
        )
    print(f"File type: {file_type}", file=output)
    print("No download or write was performed.", file=output)
    return 0


def sandbox_test_order(today: date | None = None) -> dict[str, str]:
    current_date = today or date.today()
    date_value = current_date.strftime("%m/%d/%Y")
    return {
        "order_date": date_value,
        "item_code": "SANDBOX-TEST",
        "quantity": "1",
        "color": SANDBOX_TEST_MARKER,
        "customer_name": SANDBOX_TEST_MARKER,
        "ship_by": date_value,
    }


def append_sandbox_row_to_docx(docx_bytes: bytes) -> tuple[bytes, int, int]:
    from functions.word_generator import append_orders_to_existing_docx

    return append_orders_to_existing_docx(docx_bytes, [sandbox_test_order()])


def print_write_test(
    env: Mapping[str, str],
    make_client: Callable[[str, str], SandboxOneDriveClient] = client_factory,
    output: TextIO = sys.stdout,
) -> int:
    require_write_flag(env)
    drive_id, file_id = require_sandbox_ids(env)
    apply_runtime_environment(env)
    client = make_client(drive_id, file_id)
    metadata = client.get_metadata()
    safe_name = require_sandbox_metadata(metadata)

    original_docx = client.download_docx()
    updated_docx, appended, _skipped = append_sandbox_row_to_docx(original_docx)
    if appended != 1:
        raise RuntimeError("Sandbox write expected exactly one appended row")
    client.upload_docx(updated_docx)

    print("OneDrive sandbox write test: succeeded", file=output)
    print(f"Item name: {safe_name}", file=output)
    print(f"Rows appended: {appended}", file=output)
    print(f"Marker: {SANDBOX_TEST_MARKER}", file=output)
    print("Only the configured sandbox/test file was targeted.", file=output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OneDrive sandbox test harness")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-config", action="store_true")
    modes.add_argument("--check-metadata", action="store_true")
    modes.add_argument("--write-test-row", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = merged_environment()

    try:
        if args.check_config:
            return print_config_status(env)
        if args.check_metadata:
            return print_metadata_check(env)
        if args.write_test_row:
            return print_write_test(env)
    except SafetyRefusal as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())

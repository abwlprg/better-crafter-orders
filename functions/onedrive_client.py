"""
OneDrive client for Cloud Run.

Uses a delegated Microsoft refresh token supplied by environment variables
or Secret Manager. Real Microsoft / OneDrive values must never be committed.

Required env vars:
    MS_CLIENT_ID       - Azure app client ID
    MS_REFRESH_TOKEN   - Delegated Microsoft refresh token
    ONEDRIVE_FILE_ID   - Drive item ID of the target .docx file
    ONEDRIVE_DRIVE_ID  - Drive ID from parentReference.driveId

Optional env vars:
    MS_TENANT_ID       - Defaults to "consumers" for Leo's personal account flow
    MS_CLIENT_SECRET   - Optional; not required by the current delegated flow
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SCOPES = "Files.ReadWrite offline_access"


def _required_env(key: str) -> str:
    """Read a required env var without logging its value."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    if value.lower().startswith("placeholder_"):
        raise RuntimeError(f"Environment variable {key} is still set to a placeholder")
    return value


def _tenant_id() -> str:
    """Return the Microsoft tenant ID for the delegated auth flow."""
    return os.environ.get("MS_TENANT_ID", "").strip() or "consumers"


def _get_fresh_token() -> tuple[str, str]:
    """
    Exchange the stored refresh token for a new access token.

    Returns (access_token, new_refresh_token). The caller is responsible for
    persisting the new refresh token when needed.
    """
    url = TOKEN_URL.format(tenant=_tenant_id())
    data = {
        "grant_type": "refresh_token",
        "client_id": _required_env("MS_CLIENT_ID"),
        "refresh_token": _required_env("MS_REFRESH_TOKEN"),
        "scope": SCOPES,
    }

    r = requests.post(url, data=data, timeout=30)
    r.raise_for_status()
    token_data = r.json()

    if "access_token" not in token_data:
        raise RuntimeError("Microsoft token refresh failed: access_token missing")

    new_refresh = token_data.get("refresh_token") or _required_env("MS_REFRESH_TOKEN")
    return token_data["access_token"], new_refresh


def _headers() -> dict:
    """Get auth headers with a fresh access token."""
    access_token, _ = _get_fresh_token()
    return {"Authorization": f"Bearer {access_token}"}


def _target_ids() -> tuple[str, str]:
    """Return OneDrive target identifiers from required env vars."""
    return _required_env("ONEDRIVE_DRIVE_ID"), _required_env("ONEDRIVE_FILE_ID")


def download_docx() -> bytes:
    """Download the target .docx file from OneDrive and return its raw bytes."""
    drive_id, file_id = _target_ids()
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}/content"
    r = requests.get(url, headers=_headers(), timeout=60)
    r.raise_for_status()
    logger.info("Downloaded docx (%d bytes) from OneDrive", len(r.content))
    return r.content


def upload_docx(content: bytes) -> None:
    """Upload (replace) the target .docx file on OneDrive with new content.

    Retries up to 5 times on 423 Locked errors (file open by someone).
    """
    drive_id, file_id = _target_ids()
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}/content"
    headers = _headers()
    headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    for attempt in range(1, 6):
        r = requests.put(url, headers=headers, data=content, timeout=120)
        if r.status_code == 423:
            wait = attempt * 10  # 10s, 20s, 30s, 40s, 50s
            logger.warning(
                "OneDrive file locked (423) on attempt %d/5; retrying in %ds",
                attempt,
                wait,
            )
            time.sleep(wait)
            headers = _headers()
            headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            continue
        r.raise_for_status()
        logger.info("Uploaded updated docx to OneDrive (attempt %d)", attempt)
        return

    raise RuntimeError("OneDrive file is locked after 5 retries; close the file and try again")


def download_item(drive_id: str, file_id: str) -> bytes:
    """Download a drive item by explicit drive_id and file_id.

    Raises FileNotFoundError on 404.
    Never reads ONEDRIVE_DRIVE_ID / ONEDRIVE_FILE_ID from env.
    """
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}/content"
    r = requests.get(url, headers=_headers(), timeout=60)
    if r.status_code == 404:
        raise FileNotFoundError("OneDrive item not found (404)")
    r.raise_for_status()
    logger.info("Downloaded item (%d bytes)", len(r.content))
    return r.content


def upload_item(drive_id: str, file_id: str, content: bytes) -> None:
    """Upload (replace) a drive item by explicit drive_id and file_id.

    Never reads ONEDRIVE_DRIVE_ID / ONEDRIVE_FILE_ID from env.
    Raises RuntimeError on 423 Locked rather than retrying, since sandbox
    files should not be open during automated operations.
    """
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}/content"
    headers = _headers()
    headers["Content-Type"] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    r = requests.put(url, headers=headers, data=content, timeout=120)
    if r.status_code == 423:
        raise RuntimeError("OneDrive item is locked (423) — close the file and retry")
    r.raise_for_status()
    logger.info("Uploaded item (%d bytes)", len(content))


def list_folder_children(drive_id: str, folder_id: str) -> list[dict]:
    """Return all children of a folder, following pagination automatically."""
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}/children"
    items: list[dict] = []
    while url:
        r = requests.get(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items


def delete_item(drive_id: str, file_id: str) -> None:
    """Delete a OneDrive drive item by explicit drive_id and file_id.

    Raises FileNotFoundError if the item does not exist (404).
    Raises RuntimeError for other HTTP failures.
    Never reads ONEDRIVE_DRIVE_ID / ONEDRIVE_FILE_ID from env — callers
    must supply explicit IDs so production IDs are never used accidentally.
    """
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}"
    r = requests.delete(url, headers=_headers(), timeout=30)
    if r.status_code == 404:
        raise FileNotFoundError("OneDrive item not found (already deleted or never existed)")
    try:
        r.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Microsoft Graph delete failed with HTTP {r.status_code}"
        ) from exc
    logger.info("Deleted OneDrive item (drive redacted, file redacted)")


def get_file_name() -> str:
    """Return the display name of the target file for logging/confirmation."""
    drive_id, file_id = _target_ids()
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}"
    r = requests.get(url, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json().get("name", "unknown.docx")

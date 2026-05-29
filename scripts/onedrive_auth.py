"""
ONE-TIME SETUP: OneDrive authentication via Device Code Flow.

Run this only during an approved credential setup session. It starts a Microsoft
device-code login and saves the refresh token to a local ignored file for
copying into local .env or a secret manager.

Required env vars:
    MS_CLIENT_ID

Optional env vars:
    MS_TENANT_ID          Defaults to consumers for personal Microsoft accounts
    ONEDRIVE_SHARED_URL   Shared OneDrive folder URL used only to list .docx files

Usage:
    python3 scripts/onedrive_auth.py
"""

from __future__ import annotations

import base64
import json
import os

import msal
import requests

TOKEN_FILE = ".onedrive_token"
TARGET_CANDIDATES_FILE = ".onedrive_target_candidates.json"
SCOPES = ["Files.ReadWrite"]  # MSAL adds offline_access automatically


def _required_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    if value.lower().startswith("placeholder_"):
        raise RuntimeError(f"Environment variable {key} is still set to a placeholder")
    return value


def _tenant_id() -> str:
    return os.environ.get("MS_TENANT_ID", "").strip() or "consumers"


def _authority() -> str:
    return f"https://login.microsoftonline.com/{_tenant_id()}"


def encode_share_url(url: str) -> str:
    b64 = base64.b64encode(url.encode()).decode()
    return "u!" + b64.rstrip("=").replace("/", "_").replace("+", "-")


def get_token_via_device_flow() -> dict:
    app = msal.PublicClientApplication(_required_env("MS_CLIENT_ID"), authority=_authority())

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("Token obtained from cache")
            return result

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")

    link = flow.get("verification_uri_complete") or flow["verification_uri"]

    print("\n" + "=" * 60)
    print("Send this Microsoft device-code link to Leo:")
    print(f"\n   {link}\n")
    print("Leo should sign in with the approved Microsoft account.")
    print(f"\n   Manual code if needed: {flow['user_code']}")
    print("=" * 60)
    print("\nWaiting for login...\n")

    return app.acquire_token_by_device_flow(flow)


def save_token(token_data: dict) -> None:
    """Save refresh token to a local ignored file."""
    to_save = {
        "refresh_token": token_data.get("refresh_token"),
        "client_id": os.environ.get("MS_CLIENT_ID", ""),
        "tenant_id": _tenant_id(),
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
    print(f"Token saved to {TOKEN_FILE}")


def find_docx_in_folder(access_token: str) -> list:
    """List .docx files in a shared OneDrive folder when ONEDRIVE_SHARED_URL is set."""
    share_url = os.environ.get("ONEDRIVE_SHARED_URL", "").strip()
    if not share_url:
        print("ONEDRIVE_SHARED_URL is not set; skipping folder listing.")
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    encoded = encode_share_url(share_url)
    url = f"https://graph.microsoft.com/v1.0/shares/{encoded}/driveItem/children"
    r = requests.get(url, headers=headers, timeout=30)

    if r.status_code != 200:
        print(f"Could not list folder: {r.status_code} {r.text[:300]}")
        return []

    items = r.json().get("value", [])
    docx_files = []
    print(f"\nFiles in shared folder ({len(items)} items):")
    for item in items:
        name = item["name"]
        item_id = item["id"]
        drive_id = item.get("parentReference", {}).get("driveId", "")
        print(f"   {name}")
        if name.endswith(".docx"):
            docx_files.append({"name": name, "id": item_id, "drive_id": drive_id})

    return docx_files


if __name__ == "__main__":
    print("OneDrive One-Time Authentication Setup")
    print("-" * 60)

    result = get_token_via_device_flow()

    if "access_token" not in result:
        print("\nAuthentication failed:")
        print(result.get("error_description", str(result)))
        raise SystemExit(1)

    print("Authentication successful.\n")
    save_token(result)

    print("\n" + "=" * 60)
    print("Refresh token obtained. Store it as MS_REFRESH_TOKEN in local .env or Secret Manager.")
    print("Do not paste this value into chat, docs, commits, screenshots, or logs.")
    print(f"The token was saved locally in {TOKEN_FILE}; do not commit that file.")
    print("=" * 60)

    docx_files = find_docx_in_folder(result["access_token"])

    if docx_files:
        print(f"\nFound {len(docx_files)} .docx file(s):")
        for f in docx_files:
            print(f"\n   Name:     {f['name']}")
        with open(TARGET_CANDIDATES_FILE, "w", encoding="utf-8") as f:
            json.dump(docx_files, f, indent=2)
        print(f"\nTarget IDs were saved locally in {TARGET_CANDIDATES_FILE}; do not commit that file.")
        print("\nSave the selected target IDs as ONEDRIVE_FILE_ID and ONEDRIVE_DRIVE_ID in local .env or Secret Manager.")

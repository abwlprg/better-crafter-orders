"""
ONE-TIME SETUP: OneDrive authentication via Device Code Flow.

Run this script ONCE. Leo will see a code and a URL, open the URL in a browser,
enter the code, and log in with bettercrafter1@gmail.com (Microsoft account).

The script will then save the refresh token to .onedrive_token (local file)
and print it so you can store it as MS_REFRESH_TOKEN in Cloud Run secrets.

The refresh token auto-renews every time the system uses it — Leo never needs
to log in again.

Usage:
    python3 scripts/onedrive_auth.py
"""

import json
import msal
import requests
import base64
import os

CLIENT_ID  = "61c787fc-4991-49b4-a14c-bd14117ebdfd"
TENANT_ID  = "f55fc05a-233d-4564-92ec-3b929554dbed"
TOKEN_FILE = ".onedrive_token"

AUTHORITY = "https://login.microsoftonline.com/consumers"  # personal MSA accounts
SCOPES    = ["Files.ReadWrite"]  # MSAL adds offline_access automatically

# The shared OneDrive folder link (decoded from the shared URL)
SHARE_URL = "https://1drv.ms/f/c/9f9c6569035a2b06/IgCZsgEbLxMCTLLmEDDgoVRgATF_fY6_gpnDXoyfPTIBKSg?e=AWsgHa"


def encode_share_url(url: str) -> str:
    b64 = base64.b64encode(url.encode()).decode()
    return "u!" + b64.rstrip("=").replace("/", "_").replace("+", "-")


def get_token_via_device_flow() -> dict:
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

    # Check if we already have a cached token
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("✅ Token obtained from cache")
            return result

    # Device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise Exception(f"Failed to start device flow: {flow}")

    # verification_uri_complete already has the code embedded — just open and login
    link = flow.get("verification_uri_complete") or flow["verification_uri"]

    print("\n" + "=" * 60)
    print("🔗 Envíale ESTE LINK a Leo (tiene el código ya incluido):")
    print(f"\n   {link}\n")
    print(f"👤 Leo solo abre el link e inicia sesión con: bettercrafter1@gmail.com")
    print(f"\n   (Código manual por si acaso: {flow['user_code']})")
    print("=" * 60)
    print("\nEsperando que Leo haga login...\n")

    result = app.acquire_token_by_device_flow(flow)
    return result


def save_token(token_data: dict):
    """Save refresh token to local file."""
    to_save = {
        "refresh_token": token_data.get("refresh_token"),
        "client_id":     CLIENT_ID,
        "tenant_id":     TENANT_ID,
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(to_save, f, indent=2)
    print(f"✅ Token saved to {TOKEN_FILE}")


def find_docx_in_folder(access_token: str) -> list:
    """List .docx files in the shared OneDrive Orders folder."""
    headers = {"Authorization": f"Bearer {access_token}"}
    encoded = encode_share_url(SHARE_URL)

    # Get folder contents via sharing link
    url = f"https://graph.microsoft.com/v1.0/shares/{encoded}/driveItem/children"
    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        print(f"⚠️  Could not list folder: {r.status_code} {r.text[:300]}")
        # Try /me/drive as fallback
        r2 = requests.get("https://graph.microsoft.com/v1.0/me/drive/root/children", headers=headers)
        print(f"   /me/drive/root: {r2.status_code} {r2.text[:300]}")
        return []

    items = r.json().get("value", [])
    docx_files = []
    print(f"\n📁 Files in Orders folder ({len(items)} items):")
    for item in items:
        name = item["name"]
        item_id = item["id"]
        drive_id = item.get("parentReference", {}).get("driveId", "")
        icon = "📄" if item.get("file") else "📁"
        print(f"   {icon} {name}  (id={item_id})")
        if name.endswith(".docx"):
            docx_files.append({"name": name, "id": item_id, "drive_id": drive_id})

    return docx_files


if __name__ == "__main__":
    print("🔐 OneDrive One-Time Authentication Setup")
    print("─" * 60)

    result = get_token_via_device_flow()

    if "access_token" not in result:
        print(f"\n❌ Authentication failed:")
        print(result.get("error_description", str(result)))
        exit(1)

    print("✅ Authentication successful!\n")

    # Save token
    save_token(result)

    # Print refresh token for Cloud Run env var
    refresh_token = result.get("refresh_token", "")
    print("\n" + "=" * 60)
    print("🔑 REFRESH TOKEN (save as MS_REFRESH_TOKEN in Cloud Run):")
    print(f"\n{refresh_token}\n")
    print("=" * 60)

    # Find .docx files
    docx_files = find_docx_in_folder(result["access_token"])

    if docx_files:
        print(f"\n✅ Found {len(docx_files)} .docx file(s):")
        for f in docx_files:
            print(f"\n   Name:     {f['name']}")
            print(f"   ID:       {f['id']}")
            print(f"   Drive ID: {f['drive_id']}")
        print("\n📌 Save the ID of the target file as ONEDRIVE_FILE_ID in Cloud Run.")
    else:
        print("\n⚠️  No .docx files found in the shared folder.")
        print("   Make sure Leo shared the correct folder.")

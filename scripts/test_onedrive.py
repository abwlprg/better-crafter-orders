"""Test completo de acceso a OneDrive via Microsoft Graph (app-only / client credentials).

Requiere que Ben haya agregado el permiso Application: Files.ReadWrite.All
y hecho "Grant admin consent" en Azure Portal.
"""

import msal
import os
import requests
import sys

CLIENT_ID     = os.environ.get("MS_CLIENT_ID", "")
TENANT_ID     = os.environ.get("MS_TENANT_ID", "")
CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")

AUTHORITY  = f"https://login.microsoftonline.com/{TENANT_ID}"
GRAPH_URL  = "https://graph.microsoft.com/v1.0"


def get_token() -> str:
    app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        print("❌ Auth failed:")
        print(result.get("error_description", result))
        sys.exit(1)
    print("✅ Step 1/4 — Got access token")
    return result["access_token"]


def test_list_users(headers: dict) -> str | None:
    """Lista usuarios del tenant para obtener el user_id de Ben."""
    r = requests.get(f"{GRAPH_URL}/users", headers=headers)
    if r.status_code != 200:
        print(f"❌ Step 2/4 — Cannot list users: {r.status_code} {r.text[:200]}")
        print("   → Likely missing Application permission 'User.Read.All'")
        print("   → Trying with known email instead...")
        return None
    users = r.json().get("value", [])
    print(f"✅ Step 2/4 — Found {len(users)} user(s) in tenant:")
    for u in users:
        print(f"   👤 {u.get('displayName')} — {u.get('mail') or u.get('userPrincipalName')} — id={u['id']}")
    return users[0]["id"] if users else None


def test_onedrive(headers: dict, user_id: str | None):
    """Lista archivos del OneDrive del usuario."""
    if user_id:
        url = f"{GRAPH_URL}/users/{user_id}/drive/root/children"
    else:
        # Fallback: try with email directly
        url = f"{GRAPH_URL}/users/leobaney@gmail.com/drive/root/children"

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"❌ Step 3/4 — Cannot access OneDrive: {r.status_code}")
        print(f"   {r.text[:400]}")
        print("\n   → Ben needs to add Application permission 'Files.ReadWrite.All'")
        print("   → and click 'Grant admin consent' in Azure Portal")
        return

    items = r.json().get("value", [])
    print(f"✅ Step 3/4 — OneDrive accessible! Found {len(items)} item(s) at root:")
    for item in items:
        kind = "📁" if "folder" in item else "📄"
        print(f"   {kind} {item['name']}  id={item['id']}")


def search_docx(headers: dict, user_id: str | None):
    """Busca archivos .docx (el archivo de Steven)."""
    if user_id:
        url = f"{GRAPH_URL}/users/{user_id}/drive/root/search(q='Steven')"
    else:
        url = f"{GRAPH_URL}/users/leobaney@gmail.com/drive/root/search(q='Steven')"

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"❌ Step 4/4 — Search failed: {r.status_code} {r.text[:200]}")
        return

    items = r.json().get("value", [])
    docx = [i for i in items if i["name"].endswith(".docx")]
    if not docx:
        print("⚠️  Step 4/4 — No .docx files found matching 'Steven'")
        return

    print(f"✅ Step 4/4 — Found {len(docx)} .docx file(s):")
    for item in docx:
        path = item.get("parentReference", {}).get("path", "?")
        print(f"   📄 {item['name']}")
        print(f"       path: {path}")
        print(f"       id:   {item['id']}")


if __name__ == "__main__":
    print("═" * 60)
    print("🧪 Testing Microsoft Graph + OneDrive access")
    print("═" * 60 + "\n")

    headers = {"Authorization": f"Bearer {get_token()}"}
    user_id = test_list_users(headers)
    test_onedrive(headers, user_id)
    search_docx(headers, user_id)

    print("\n" + "═" * 60)

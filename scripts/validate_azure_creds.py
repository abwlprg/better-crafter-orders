"""Validar credenciales de Azure usando Client Credentials flow.

Este flow NO requiere permisos delegated, ni redirect URI, ni device code.
Solo valida que: client_id + tenant_id + client_secret son válidos.

Si esto funciona → las credenciales están bien
Si falla → hay un typo en alguno de los IDs
"""

import msal
import os
import sys

CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
TENANT_ID = os.environ.get("MS_TENANT_ID", "")
CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

print(f"🔐 Validating credentials...")
print(f"   Client ID:  {CLIENT_ID}")
print(f"   Tenant ID:  {TENANT_ID}")
print(f"   Authority:  {AUTHORITY}")
print()

app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET,
)

# Trying to get a token for Microsoft Graph using client credentials
result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

if "access_token" in result:
    print("✅ Credentials are VALID — got an access token")
    print(f"   Token expires in: {result.get('expires_in')} seconds")
    sys.exit(0)
else:
    print("❌ FAILED:")
    print(f"   error: {result.get('error')}")
    print(f"   description: {result.get('error_description', '')[:300]}")
    sys.exit(1)

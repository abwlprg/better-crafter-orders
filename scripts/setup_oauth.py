"""
Gmail OAuth setup — diseñado para correr en TU MAC LOCAL.

Uso:
    python3 scripts/setup_oauth.py

Qué hace automáticamente:
  1. Abre tu browser en la Mac (loopback OAuth — el método recomendado por Google).
  2. Inicias sesión con bettercrafter1@gmail.com y autorizas.
  3. Captura el refresh_token.
  4. Guarda el token en Google Secret Manager (crea el secret si no existe).
  5. Actualiza la variable de entorno GMAIL_REFRESH_TOKEN en Cloud Run.
  6. Renueva el Gmail push-watch para reactivar los webhooks.

Requisitos:
  - gcloud CLI instalado y autenticado (gcloud auth login).
  - Acceso al proyecto ordersbc-494213.
  - Las credenciales del cliente Desktop (gmail-desktop) en ./client_secret_*.json
    o en variables de entorno GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET.

Por qué NO se corre en Cloud Shell:
  Google deprecó el flujo OOB (copy-paste de código). El método actual requiere
  un servidor local en 127.0.0.1, al cual tu browser debe poder conectarse —
  imposible desde Cloud Shell sin port-forwarding manual.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Configuración ──────────────────────────────────────────────────────────────
PROJECT_ID    = "ordersbc-494213"
REGION        = "us-central1"
SERVICE_NAME  = "order-app"
SERVICE_URL   = f"https://{SERVICE_NAME}-363114180511.{REGION}.run.app"
SECRET_NAME   = "GMAIL_REFRESH_TOKEN"
GMAIL_SCOPE   = "https://www.googleapis.com/auth/gmail.readonly"
LOOPBACK_PORT = 8765  # puerto local para recibir el redirect

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLIENT_SECRET = ROOT / "client_secret_363114180511-r3cttlssveajnu1h4pismlod2v5f1qmj.apps.googleusercontent.com.json"


def _load_client_credentials() -> tuple[str, str]:
    """Lee client_id/secret desde el JSON descargado o desde env vars."""
    cid = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    csecret = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()

    if cid and csecret:
        return cid, csecret

    if DEFAULT_CLIENT_SECRET.exists():
        data = json.loads(DEFAULT_CLIENT_SECRET.read_text())
        block = data.get("installed") or data.get("web") or {}
        cid = block.get("client_id", "")
        csecret = block.get("client_secret", "")
        if cid and csecret:
            print(f"✓ Credenciales leídas de {DEFAULT_CLIENT_SECRET.name}")
            return cid, csecret

    print("\n⚠️  No se encontraron credenciales.")
    print("   Coloca el archivo client_secret_*.json en la raíz del proyecto,")
    print("   o exporta GMAIL_CLIENT_ID y GMAIL_CLIENT_SECRET.")
    cid = input("\nGMAIL_CLIENT_ID: ").strip()
    csecret = input("GMAIL_CLIENT_SECRET: ").strip()
    return cid, csecret


def run_oauth_flow(client_id: str, client_secret: str) -> str:
    """Loopback OAuth flow — abre el browser local y captura el redirect."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Instalando google-auth-oauthlib...")
        subprocess.run([sys.executable, "-m", "pip", "install", "google-auth-oauthlib", "-q"], check=True)
        from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [f"http://localhost:{LOOPBACK_PORT}", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=[GMAIL_SCOPE])

    print("\n" + "═" * 60)
    print("🔐 Abriendo browser para autorización...")
    print("   Inicia sesión con: bettercrafter1@gmail.com")
    print("═" * 60 + "\n")

    credentials = flow.run_local_server(
        port=LOOPBACK_PORT,
        access_type="offline",
        prompt="consent",
        open_browser=True,
        success_message="✅ Autorización exitosa. Puedes cerrar esta pestaña.",
    )

    if not credentials.refresh_token:
        raise RuntimeError(
            "❌ No se recibió refresh_token.\n"
            "   Revoca el acceso en https://myaccount.google.com/permissions\n"
            "   y vuelve a correr este script."
        )

    return credentials.refresh_token


def save_to_secret_manager(refresh_token: str) -> None:
    """Guarda el refresh_token en Secret Manager (crea o actualiza)."""
    print(f"\n📦 Guardando en Secret Manager ({SECRET_NAME})...")

    check = subprocess.run(
        ["gcloud", "secrets", "describe", SECRET_NAME, f"--project={PROJECT_ID}"],
        capture_output=True, text=True
    )

    if check.returncode != 0:
        subprocess.run(
            ["gcloud", "secrets", "create", SECRET_NAME,
             f"--project={PROJECT_ID}", "--replication-policy=automatic"],
            check=True
        )
        print(f"   ✅ Secret '{SECRET_NAME}' creado")

    subprocess.run(
        ["gcloud", "secrets", "versions", "add", SECRET_NAME,
         f"--project={PROJECT_ID}", "--data-file=-"],
        input=refresh_token, text=True, check=True
    )
    print("   ✅ Nueva versión guardada")


def update_cloud_run_env(refresh_token: str) -> None:
    """Actualiza GMAIL_REFRESH_TOKEN en Cloud Run."""
    print(f"\n🚀 Actualizando Cloud Run ({SERVICE_NAME})...")
    subprocess.run(
        [
            "gcloud", "run", "services", "update", SERVICE_NAME,
            f"--region={REGION}",
            f"--project={PROJECT_ID}",
            f"--update-env-vars=GMAIL_REFRESH_TOKEN={refresh_token}",
        ],
        check=True,
    )
    print("   ✅ Variable de entorno actualizada")


def renew_gmail_watch() -> None:
    """Llama al endpoint /api/renew-gmail-watch para reactivar webhooks."""
    print("\n📡 Renovando Gmail push-watch...")
    try:
        import urllib.request
        url = f"{SERVICE_URL}/api/renew-gmail-watch"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            print(f"   ✅ Watch renovado: {body[:120]}")
    except Exception as e:
        print(f"   ⚠️  No se pudo renovar el watch automáticamente: {e}")
        print(f"   Renueva manualmente: curl -X POST {SERVICE_URL}/api/renew-gmail-watch")


def main() -> None:
    print("═" * 60)
    print("🔧 Gmail OAuth Setup — Better Crafter Orders")
    print("═" * 60)

    client_id, client_secret = _load_client_credentials()

    refresh_token = run_oauth_flow(client_id, client_secret)
    print(f"\n✅ Refresh token obtenido: {refresh_token[:25]}...")

    save_to_secret_manager(refresh_token)
    update_cloud_run_env(refresh_token)
    renew_gmail_watch()

    print("\n" + "═" * 60)
    print("🎉 ¡Todo actualizado! El sistema debería funcionar ahora.")
    print(f"   Verifica logs: gcloud run services logs read {SERVICE_NAME} \\")
    print(f"     --project={PROJECT_ID} --region={REGION} --limit=20")
    print("═" * 60)


if __name__ == "__main__":
    main()


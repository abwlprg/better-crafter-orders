"""
Gmail OAuth setup — funciona en Cloud Shell y localmente.

Uso:
    python3 scripts/setup_oauth.py

Qué hace automáticamente:
  1. Lee client_id / client_secret de las variables de entorno de Cloud Run
     (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET) — sin necesidad de subir archivos.
  2. Abre un URL para que autorices en el browser y pides pegar el código de vuelta.
  3. Guarda el nuevo refresh_token en Secret Manager (crea el secret si no existe).
  4. Actualiza la variable de entorno GMAIL_REFRESH_TOKEN en Cloud Run.
  5. Renueva el Gmail push-watch para reactivar los webhooks.

Para correr en Cloud Shell (sin subir ningún archivo):
    gcloud run services describe order-app --region=us-central1 \\
        --format='value(spec.template.spec.containers[0].env)' | grep GMAIL
    python3 scripts/setup_oauth.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# ── Configuración ──────────────────────────────────────────────────────────────
PROJECT_ID   = "ordersbc-494213"
REGION       = "us-central1"
SERVICE_NAME = "order-app"
SECRET_NAME  = "GMAIL_REFRESH_TOKEN"
GMAIL_SCOPE  = "https://www.googleapis.com/auth/gmail.readonly"

# Client credentials: se leen de env vars si están disponibles,
# o se piden al usuario como fallback.
CLIENT_ID     = os.environ.get("GMAIL_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()


def _get_client_credentials() -> tuple[str, str]:
    """Lee client_id y client_secret desde env o los pide al usuario."""
    cid = CLIENT_ID
    csecret = CLIENT_SECRET

    if not cid:
        print("\n⚠️  GMAIL_CLIENT_ID no encontrado en env vars.")
        print("   Puedes obtenerlo con:")
        print(f"   gcloud run services describe {SERVICE_NAME} --region={REGION} "
              "--format='value(spec.template.spec.containers[0].env)'")
        cid = input("\nPega el GMAIL_CLIENT_ID aquí: ").strip()

    if not csecret:
        csecret = input("Pega el GMAIL_CLIENT_SECRET aquí: ").strip()

    return cid, csecret


def run_oauth_flow(client_id: str, client_secret: str) -> str:
    """Flujo OAuth con copy-paste — funciona en Cloud Shell sin browser local."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        print("Instalando google-auth-oauthlib...")
        subprocess.run([sys.executable, "-m", "pip", "install", "google-auth-oauthlib", "-q"], check=True)
        from google_auth_oauthlib.flow import Flow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=[GMAIL_SCOPE],
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print("\n" + "═" * 60)
    print("🔐 AUTORIZACIÓN REQUERIDA")
    print("═" * 60)
    print("\n1. Abre este URL en tu browser:")
    print(f"\n   {auth_url}\n")
    print("2. Inicia sesión con bettercrafter1@gmail.com")
    print("3. Autoriza el acceso")
    print("4. Copia el código que aparece y pégalo aquí\n")

    code = input("Código de autorización: ").strip()
    flow.fetch_token(code=code)

    credentials = flow.credentials
    if not credentials.refresh_token:
        raise RuntimeError(
            "❌ No se recibió refresh_token. "
            "Revoca el acceso en https://myaccount.google.com/permissions y vuelve a intentar."
        )

    return credentials.refresh_token


def save_to_secret_manager(refresh_token: str) -> None:
    """Guarda el refresh_token en Secret Manager (crea o actualiza el secret)."""
    print(f"\n📦 Guardando en Secret Manager ({SECRET_NAME})...")

    # Verificar si el secret existe
    check = subprocess.run(
        ["gcloud", "secrets", "describe", SECRET_NAME, f"--project={PROJECT_ID}"],
        capture_output=True, text=True
    )

    if check.returncode != 0:
        # Crear el secret
        subprocess.run(
            ["gcloud", "secrets", "create", SECRET_NAME,
             f"--project={PROJECT_ID}", "--replication-policy=automatic"],
            check=True
        )
        print(f"   ✅ Secret '{SECRET_NAME}' creado")

    # Agregar nueva versión
    proc = subprocess.run(
        ["gcloud", "secrets", "versions", "add", SECRET_NAME,
         f"--project={PROJECT_ID}", "--data-file=-"],
        input=refresh_token, text=True, check=True
    )
    print(f"   ✅ Nueva versión guardada en Secret Manager")


def update_cloud_run_env(refresh_token: str) -> None:
    """Actualiza la variable GMAIL_REFRESH_TOKEN en Cloud Run."""
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
    print("   ✅ Cloud Run actualizado con el nuevo token")


def renew_gmail_watch() -> None:
    """Llama al endpoint /api/renew-gmail-watch para reactivar los webhooks."""
    print("\n📡 Renovando Gmail push-watch...")
    try:
        import urllib.request
        url = f"https://{SERVICE_NAME}-363114180511.{REGION}.run.app/api/renew-gmail-watch"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            print(f"   ✅ Watch renovado: {body[:100]}")
    except Exception as e:
        print(f"   ⚠️  No se pudo renovar el watch automáticamente: {e}")
        print("   Puedes renovarlo manualmente corriendo:")
        print(f"   curl -X POST https://{SERVICE_NAME}-363114180511.{REGION}.run.app/api/renew-gmail-watch")


def main() -> None:
    print("═" * 60)
    print("🔧 Gmail OAuth Setup — Better Crafter Orders")
    print("═" * 60)

    client_id, client_secret = _get_client_credentials()

    # 1. Obtener nuevo refresh token
    refresh_token = run_oauth_flow(client_id, client_secret)
    print(f"\n✅ Refresh token obtenido: {refresh_token[:20]}...")

    # 2. Guardar en Secret Manager
    save_to_secret_manager(refresh_token)

    # 3. Actualizar Cloud Run
    update_cloud_run_env(refresh_token)

    # 4. Renovar Gmail watch
    renew_gmail_watch()

    print("\n" + "═" * 60)
    print("🎉 ¡Todo actualizado! El sistema debería funcionar ahora.")
    print("   Verifica los logs con:")
    print(f"   gcloud run services logs read {SERVICE_NAME} --project={PROJECT_ID} --region={REGION} --limit=20")
    print("═" * 60)


if __name__ == "__main__":
    main()


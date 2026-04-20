"""Test en vivo — conecta a Gmail real y lee los correos enviados a Stephen."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Cargar .env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(Path(__file__).parent))

from functions.gmail_client import GmailClient
from functions.email_parser import PARSER_REGISTRY
from functions import config

STEPHEN_EMAIL = os.getenv("STEPHEN_EMAIL", config.STEPHEN_EMAIL)


def main() -> None:
    print("=" * 52)
    print("  TEST EN VIVO — Leyendo Gmail real")
    print(f"  Cuenta: {config.GMAIL_ACCOUNT}")
    print(f"  Proveedor: {STEPHEN_EMAIL}")
    print("=" * 52)

    client_id = os.environ["GMAIL_CLIENT_ID"]
    client_secret = os.environ["GMAIL_CLIENT_SECRET"]
    refresh_token = os.environ["GMAIL_REFRESH_TOKEN"]

    print("\n── Conectando a Gmail API...")
    gmail = GmailClient(
        gmail_account=config.GMAIL_ACCOUNT,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    print("✅ Conexión exitosa")

    print(f"\n── Buscando correos enviados a {STEPHEN_EMAIL} (últimas {config.SEARCH_HOURS_BACK}h)...")
    messages = gmail.list_supplier_messages(
        supplier_email=STEPHEN_EMAIL,
        hours_back=config.SEARCH_HOURS_BACK,
    )

    if not messages:
        print("⚠️  No se encontraron correos en ese período.")
        print("   Prueba cambiando SEARCH_HOURS_BACK en config.py o verifica el email del proveedor.")
        return

    print(f"✅ {len(messages)} correo(s) encontrado(s)\n")

    parser = PARSER_REGISTRY["stephen"]

    for i, msg in enumerate(messages, 1):
        print(f"── Correo #{i} (ID: {msg.message_id}) ──────────────")
        print(f"Cuerpo:\n{msg.body[:300]}{'...' if len(msg.body) > 300 else ''}\n")

        parsed = parser.parse(msg.body)
        if parsed:
            print("✅ Parseado correctamente:")
            for k, v in parsed.items():
                print(f"   {k}: {v}")
        else:
            print("❌ No coincide con el formato esperado de Stephen")
        print()


if __name__ == "__main__":
    main()

"""Diagnóstico Gmail — muestra los últimos correos enviados sin filtros."""

from __future__ import annotations

import os
import sys
from pathlib import Path

env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(Path(__file__).parent))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from functions import config

creds = Credentials(
    token=None,
    refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
    token_uri=config.GMAIL_TOKEN_URI,
    client_id=os.environ["GMAIL_CLIENT_ID"],
    client_secret=os.environ["GMAIL_CLIENT_SECRET"],
    scopes=[config.GMAIL_READONLY_SCOPE],
)
creds.refresh(Request())
service = build("gmail", "v1", credentials=creds, cache_discovery=False)

print("── Últimos 10 correos enviados (sin filtro) ─────")
result = service.users().messages().list(
    userId=config.GMAIL_ACCOUNT,
    q="in:sent",
    maxResults=10,
).execute()

messages = result.get("messages", [])
if not messages:
    print("⚠️  No hay correos enviados en esta cuenta.")
else:
    for ref in messages:
        msg = service.users().messages().get(
            userId=config.GMAIL_ACCOUNT,
            id=ref["id"],
            format="metadata",
            metadataHeaders=["To", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        print(f"  To:      {headers.get('To', 'N/A')}")
        print(f"  Subject: {headers.get('Subject', 'N/A')}")
        print(f"  Date:    {headers.get('Date', 'N/A')}")
        print()

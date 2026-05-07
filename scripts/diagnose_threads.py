"""
Diagnóstico de hilos con múltiples mensajes.

Busca correos enviados a Stephen donde el mismo thread tiene >1 mensaje,
y muestra:
  - Qué cuerpo habría procesado el sistema ANTES del fix (cualquier mensaje)
  - Qué cuerpo procesará DESPUÉS del fix (el más antiguo del hilo)
  - Si el parser extrae datos del primer mensaje correctamente

Uso:
    cd /Users/1di/order_system_automatition/scripts
    /opt/homebrew/opt/python@3.11/bin/python3.11 diagnose_threads.py [días_hacia_atrás]

Default: 30 días.
"""

from __future__ import annotations

import base64
import math
import os
import re
import sys
import time
from pathlib import Path

# ── Load .env (search upward from this script's location) ─────────────────
_script_dir = Path(__file__).resolve().parent
for _candidate in [_script_dir / ".env", _script_dir.parent / ".env", _script_dir.parent / "functions" / ".env"]:
    if _candidate.exists():
        for line in _candidate.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
        break

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

GMAIL_ACCOUNT  = os.environ.get("GMAIL_ACCOUNT",  "bettercrafterorders@gmail.com")
SUPPLIER_EMAIL = os.environ.get("STEPHEN_EMAIL",   "7173783020@hellofax.com")
DAYS_BACK      = int(sys.argv[1]) if len(sys.argv) > 1 else 30

# ── Auth ───────────────────────────────────────────────────────────────────
creds = Credentials(
    token=None,
    refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.environ["GMAIL_CLIENT_ID"],
    client_secret=os.environ["GMAIL_CLIENT_SECRET"],
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
)
creds.refresh(Request())
service = build("gmail", "v1", credentials=creds, cache_discovery=False)

# ── Helpers ────────────────────────────────────────────────────────────────

def decode_body(payload: dict) -> str:
    def find_plain(p):
        if p.get("mimeType") == "text/plain":
            data = p.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        for part in p.get("parts", []) or []:
            found = find_plain(part)
            if found:
                return found
        return ""

    def find_html(p):
        if p.get("mimeType") == "text/html":
            data = p.get("body", {}).get("data")
            if data:
                html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                return BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)
        for part in p.get("parts", []) or []:
            found = find_html(part)
            if found:
                return found
        return ""

    return find_plain(payload) or find_html(payload) or ""


SIMPLE_PATTERNS = {
    "order_date":    re.compile(r"^\s*order\s*date\s*:\s*(.+?)\s*$",    re.I | re.M),
    "color":         re.compile(r"^\s*color\s*:\s*(.+?)\s*$",           re.I | re.M),
    "ship_by":       re.compile(r"^\s*ship\s*by\s*:\s*(.+?)\s*$",       re.I | re.M),
    "customer_name": re.compile(r"^\s*customer\s*info\s*:\s*(.+?)\s*$", re.I | re.M),
    "quantity":      re.compile(r"^\s*quantity\s*:\s*(.+?)\s*$",        re.I | re.M),
}
ITEM_CODE_RE = re.compile(r"^\s*item\s*:\s*(\d[\w]*)\s*$", re.I | re.M)


def quick_parse(body: str) -> dict:
    """Quick field extraction to show what the parser would get."""
    result = {}
    for key, pat in SIMPLE_PATTERNS.items():
        m = pat.search(body)
        result[key] = m.group(1).strip() if m else None
    m = ITEM_CODE_RE.search(body)
    result["item_code"] = m.group(1).strip() if m else None
    return result


def is_valid(fields: dict) -> bool:
    return bool(fields.get("customer_name")) and bool(fields.get("item_code") or fields.get("order_date"))


# ── Fetch messages ─────────────────────────────────────────────────────────
print(f"\n{'═'*72}")
print(f"  DIAGNÓSTICO DE HILOS — Múltiples mensajes por thread")
print(f"  Cuenta  : {GMAIL_ACCOUNT}")
print(f"  A       : {SUPPLIER_EMAIL}")
print(f"  Período : últimos {DAYS_BACK} días")
print(f"{'═'*72}\n")

query = (
    f"deliveredto:bettercrafter1@gmail.com "
    f"to:{SUPPLIER_EMAIL} "
    f"has:attachment filename:pdf "
    f"newer_than:{DAYS_BACK}d"
)
print(f"🔍 Query: {query}\n")

refs = []
page_token = None
while True:
    kw = {"userId": GMAIL_ACCOUNT, "q": query, "maxResults": 500}
    if page_token:
        kw["pageToken"] = page_token
    listing = service.users().messages().list(**kw).execute()
    refs.extend(listing.get("messages", []))
    page_token = listing.get("nextPageToken")
    if not page_token:
        break

print(f"📬 Referencias encontradas: {len(refs)}\n")
print("Descargando payloads", end="", flush=True)

# group by thread
thread_data: dict[str, list[dict]] = {}   # thread_id → list of full payloads

for i, ref in enumerate(refs):
    try:
        payload = service.users().messages().get(
            userId=GMAIL_ACCOUNT, id=ref["id"], format="full"
        ).execute()
        tid = payload.get("threadId", ref["id"])
        thread_data.setdefault(tid, [])
        thread_data[tid].append(payload)
        sys.stdout.write(".")
        sys.stdout.flush()
        if (i + 1) % 50 == 0:
            sys.stdout.write(f" {i+1}/{len(refs)}\n")
        time.sleep(0.05)
    except Exception as exc:
        print(f"\n⚠️  Error fetching {ref['id']}: {exc}")

print(f"\n\n✅ Descargados {len(refs)} mensajes en {len(thread_data)} hilos únicos\n")

# ── Analyse threads ────────────────────────────────────────────────────────
multi_threads = {tid: msgs for tid, msgs in thread_data.items() if len(msgs) > 1}
single_threads = {tid: msgs for tid, msgs in thread_data.items() if len(msgs) == 1}

print(f"{'─'*72}")
print(f"  📊 Hilos con 1 mensaje  : {len(single_threads)}")
print(f"  ⚠️  Hilos con >1 mensaje : {len(multi_threads)}  ← ESTOS SON EL PROBLEMA REPORTADO")
print(f"{'─'*72}\n")

if not multi_threads:
    print("🎉 No se encontraron hilos con múltiples mensajes en el período seleccionado.")
    print(f"   Prueba con un período mayor: python3 diagnose_threads.py 60")
    sys.exit(0)

# ── Detailed report for multi-message threads ──────────────────────────────
print(f"{'═'*72}")
print(f"  DETALLE DE HILOS CON MÚLTIPLES MENSAJES")
print(f"{'═'*72}\n")

problems_fixed = 0
problems_total = 0

for thread_idx, (tid, msgs) in enumerate(multi_threads.items(), 1):
    # Sort by internalDate ascending (oldest first) — SAME as the fix
    msgs_sorted = sorted(msgs, key=lambda m: int(m.get("internalDate", 0)))

    first_msg  = msgs_sorted[0]
    other_msgs = msgs_sorted[1:]

    first_body  = decode_body(first_msg.get("payload", {}))
    first_fields = quick_parse(first_body)

    # Extract subject/date from headers
    def get_header(msg, name):
        for h in msg.get("payload", {}).get("headers", []):
            if h["name"].lower() == name.lower():
                return h["value"]
        return "?"

    print(f"{'─'*72}")
    print(f"  HILO #{thread_idx}  ID: {tid[:12]}...")
    print(f"  Mensajes en el hilo: {len(msgs)}")
    print()

    for mi, m in enumerate(msgs_sorted):
        body = decode_body(m.get("payload", {}))
        fields = quick_parse(body)
        label = "🟢 ORIGINAL (el que el fix usa)" if mi == 0 else f"🔴 RESPUESTA #{mi} (el fix LO IGNORA)"
        print(f"  [{mi+1}] {label}")
        print(f"       Message-ID : {m.get('id', '?')}")
        print(f"       Date       : {get_header(m, 'date')}")
        print(f"       Subject    : {get_header(m, 'subject')}")
        print(f"       Body ({len(body)} chars) — primeras 3 líneas:")
        for line in body.splitlines()[:3]:
            if line.strip():
                print(f"         {line.strip()}")
        print(f"       Campos encontrados:")
        for k, v in fields.items():
            status = "✅" if v else "❌"
            print(f"         {status} {k}: {v or '(vacío)'}")
        print()

    # Evaluate if fix helps
    first_valid = is_valid(first_fields)
    problems_total += 1
    if first_valid:
        problems_fixed += 1
        verdict = "✅ FIX FUNCIONA — El primer email tiene los datos del pedido"
    else:
        # Check if any other message was better
        any_other_valid = any(is_valid(quick_parse(decode_body(m.get("payload", {})))) for m in other_msgs)
        if any_other_valid:
            verdict = "⚠️  ATENCIÓN — El primer email NO tiene datos pero uno posterior sí (caso inusual)"
        else:
            verdict = "ℹ️  Ningún mensaje del hilo tiene datos completos del pedido"

    print(f"  VEREDICTO: {verdict}")
    print()

# ── Summary ────────────────────────────────────────────────────────────────
print(f"{'═'*72}")
print(f"  RESUMEN FINAL")
print(f"{'─'*72}")
print(f"  Hilos con múltiples mensajes : {problems_total}")
print(f"  Hilos donde el fix ayuda     : {problems_fixed} ✅")
print(f"  Hilos con posible problema   : {problems_total - problems_fixed} ⚠️")
print(f"{'═'*72}\n")

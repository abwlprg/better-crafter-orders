"""
Diagnóstico de hilos: muestra qué cuerpo usaría el sistema para cada pedido.

Usa threads.list + threads.get (igual que el fix) para mostrar:
  - Cuántos mensajes tiene cada hilo
  - Qué cuerpo usaría (siempre msg #1)
  - Si el parser encuentra los datos del pedido

Uso:
    cd ~/better-crafter-orders
    python3 scripts/diagnose_threads.py [días_hacia_atrás]
"""

from __future__ import annotations

import base64
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


def get_header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return "?"


def has_pdf(msg: dict) -> bool:
    def _scan(p):
        if p.get("mimeType") == "application/pdf" or (p.get("filename", "").lower().endswith(".pdf")):
            return True
        return any(_scan(c) for c in p.get("parts", []) or [])
    return _scan(msg.get("payload", {}))


SIMPLE_PATTERNS = {
    "order_date":    re.compile(r"^\s*order\s*date\s*:\s*(.+?)\s*$",    re.I | re.M),
    "customer_name": re.compile(r"^\s*customer\s*info\s*:\s*(.+?)\s*$", re.I | re.M),
    "color":         re.compile(r"^\s*color\s*:\s*(.+?)\s*$",           re.I | re.M),
    "ship_by":       re.compile(r"^\s*ship\s*by\s*:\s*(.+?)\s*$",       re.I | re.M),
}
ITEM_CODE_RE = re.compile(r"^\s*item\s*:\s*(\d[\w]*)\s*$", re.I | re.M)


def quick_parse(body: str) -> dict:
    result = {}
    for key, pat in SIMPLE_PATTERNS.items():
        m = pat.search(body)
        result[key] = m.group(1).strip() if m else None
    m = ITEM_CODE_RE.search(body)
    result["item_code"] = m.group(1).strip() if m else None
    return result


def is_valid(fields: dict) -> bool:
    return bool(fields.get("customer_name")) and bool(fields.get("item_code") or fields.get("order_date"))


# ── Fetch threads ──────────────────────────────────────────────────────────
print(f"\n{'═'*72}")
print(f"  DIAGNÓSTICO DE HILOS (threads.list + threads.get)")
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

thread_refs = []
page_token = None
while True:
    kw = {"userId": GMAIL_ACCOUNT, "q": query, "maxResults": 500}
    if page_token:
        kw["pageToken"] = page_token
    listing = service.users().threads().list(**kw).execute()
    thread_refs.extend(listing.get("threads", []))
    page_token = listing.get("nextPageToken")
    if not page_token:
        break

print(f"📬 Hilos encontrados: {len(thread_refs)}\n")
print("Descargando threads", end="", flush=True)

threads_data = []
for i, ref in enumerate(thread_refs):
    try:
        td = service.users().threads().get(
            userId=GMAIL_ACCOUNT, id=ref["id"], format="full"
        ).execute()
        threads_data.append(td)
        sys.stdout.write(".")
        sys.stdout.flush()
        if (i + 1) % 50 == 0:
            sys.stdout.write(f" {i+1}/{len(thread_refs)}\n")
        time.sleep(0.05)
    except Exception as exc:
        print(f"\n⚠️  Error fetching thread {ref['id']}: {exc}")

print(f"\n\n✅ Descargados {len(threads_data)} hilos completos\n")

# ── Analyse ────────────────────────────────────────────────────────────────
multi_msg_threads = [t for t in threads_data if len(t.get("messages", [])) > 1]
single_msg_threads = [t for t in threads_data if len(t.get("messages", [])) == 1]

print(f"{'─'*72}")
print(f"  📊 Hilos con 1 mensaje  : {len(single_msg_threads)}")
print(f"  ⚠️  Hilos con >1 mensaje : {len(multi_msg_threads)}  ← posibles afectados")
print(f"{'─'*72}\n")

# Check single-message threads that fail to parse (also a problem)
single_failures = []
for t in single_msg_threads:
    msgs = t.get("messages", [])
    body = decode_body(msgs[0].get("payload", {}))
    if not is_valid(quick_parse(body)):
        single_failures.append((t, msgs[0], body))

print(f"  ❌ Hilos de 1 msg que fallan el parse: {len(single_failures)}")
print(f"{'─'*72}\n")

# ── Detail: multi-message threads ─────────────────────────────────────────
if multi_msg_threads:
    print(f"{'═'*72}")
    print(f"  DETALLE — HILOS CON MÚLTIPLES MENSAJES")
    print(f"{'═'*72}\n")

    for ti, t in enumerate(multi_msg_threads, 1):
        msgs = t.get("messages", [])  # already oldest→newest per API
        print(f"{'─'*72}")
        print(f"  HILO #{ti}  ({len(msgs)} mensajes)")
        print()

        for mi, msg in enumerate(msgs):
            body = decode_body(msg.get("payload", {}))
            fields = quick_parse(body)
            pdf = "📎 tiene PDF" if has_pdf(msg) else "  sin PDF"
            label = "🟢 USAR ESTE (msg #1)" if mi == 0 else f"🔴 ignorar (msg #{mi+1})"
            print(f"  [{mi+1}] {label}  {pdf}")
            print(f"       Date    : {get_header(msg, 'date')}")
            print(f"       Subject : {get_header(msg, 'subject')}")
            body_preview = " | ".join(l.strip() for l in body.splitlines() if l.strip())[:120]
            print(f"       Body    : {body_preview or '(vacío)'}")
            for k, v in fields.items():
                s = "✅" if v else "❌"
                print(f"         {s} {k}: {v or '(vacío)'}")
            print()

        # Verdict
        first_body = decode_body(msgs[0].get("payload", {}))
        if is_valid(quick_parse(first_body)):
            print(f"  ✅ FIX OK — msg #1 tiene datos válidos del pedido")
        else:
            # Check if PDF is only in a later message
            first_has_pdf = has_pdf(msgs[0])
            later_has_pdf = any(has_pdf(m) for m in msgs[1:])
            if not first_has_pdf and later_has_pdf:
                print(f"  ⚠️  PDF está en reply, no en original — parser usará body de msg #1 + PDF de reply")
            else:
                print(f"  ❌ msg #1 no tiene datos parseables — revisar manualmente")
        print()

# ── Detail: single-message parse failures ─────────────────────────────────
if single_failures:
    print(f"\n{'═'*72}")
    print(f"  HILOS DE 1 MENSAJE QUE FALLAN EL PARSE ({len(single_failures)})")
    print(f"{'═'*72}\n")
    for t, msg, body in single_failures[:10]:  # show max 10
        print(f"  ID: {msg.get('id','?')}  Date: {get_header(msg,'date')}")
        print(f"  Subject: {get_header(msg,'subject')}")
        body_preview = " | ".join(l.strip() for l in body.splitlines() if l.strip())[:150]
        print(f"  Body: {body_preview or '(vacío)'}")
        fields = quick_parse(body)
        for k, v in fields.items():
            s = "✅" if v else "❌"
            print(f"    {s} {k}: {v or ''}")
        print()

print(f"\n{'═'*72}")
print(f"  FIN DEL DIAGNÓSTICO")
print(f"{'═'*72}\n")

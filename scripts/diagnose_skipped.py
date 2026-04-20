"""
Diagnostic script: shows WHY each email is being skipped.

Fetches emails WITHOUT downloading PDF attachments (fast).
For each skipped email, prints:
  - Message ID
  - Raw email body (first 600 chars)
  - Which fields were found vs missing
  - Why it was rejected

Run:
  /opt/homebrew/opt/python@3.11/bin/python3.11 diagnose_skipped.py
"""

from __future__ import annotations

import os
import re
import sys
import base64
import math
import time
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

# ── Gmail auth ─────────────────────────────────────────────────
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

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

GMAIL_ACCOUNT   = os.environ.get("GMAIL_ACCOUNT", "bettercrafterorders@gmail.com")
SUPPLIER_EMAIL  = os.environ.get("STEPHEN_EMAIL",  "7173783020@hellofax.com")
MAX_EMAILS      = 100  # same window as production

# ── Regex patterns (same as StephenParser) ─────────────────────
PATTERNS = {
    "order_date":    re.compile(r"^\s*order\s*date\s*:\s*(.+?)\s*$",     re.I | re.M),
    "color":         re.compile(r"^\s*color\s*:\s*(.+?)\s*$",            re.I | re.M),
    "ship_by":       re.compile(r"^\s*ship\s*by\s*:\s*(.+?)\s*$",        re.I | re.M),
    "customer_name": re.compile(r"^\s*customer\s*info\s*:\s*(.+?)\s*$",  re.I | re.M),
    "quantity":      re.compile(r"^\s*quantity\s*:\s*(.+?)\s*$",         re.I | re.M),
    "brand":         re.compile(r"^\s*brand\s*:\s*(.+?)\s*$",            re.I | re.M),
}
ITEM_CODE_RE  = re.compile(r"^\s*item\s*:\s*(\d[\w]*)\s*$",              re.I | re.M)
ITEM_NAME_RE  = re.compile(r"^\s*item\s*name\s*:\s*(.+?)\s*$",           re.I | re.M)


def decode_body(payload: dict) -> str:
    """Extract plain text body from Gmail payload (no PDF downloads)."""
    def find_plain(p):
        if p.get("mimeType") == "text/plain":
            data = p.get("body", {}).get("data")
            if data:
                raw = base64.urlsafe_b64decode(data + "==")
                return raw.decode("utf-8", errors="replace")
        for part in p.get("parts", []) or []:
            found = find_plain(part)
            if found:
                return found
        return ""

    def find_html(p):
        if p.get("mimeType") == "text/html":
            data = p.get("body", {}).get("data")
            if data:
                raw = base64.urlsafe_b64decode(data + "==")
                html = raw.decode("utf-8", errors="replace")
                return BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)
        for part in p.get("parts", []) or []:
            found = find_html(part)
            if found:
                return found
        return ""

    return find_plain(payload) or find_html(payload) or ""


def diagnose(body: str) -> dict:
    """Run all regex patterns and return hit/miss for each field."""
    results = {}
    for key, pat in PATTERNS.items():
        m = pat.search(body)
        results[key] = m.group(1).strip() if m else None

    # item_code
    m = ITEM_CODE_RE.search(body)
    results["item_code"] = m.group(1).strip() if m else None

    # item_name
    m = ITEM_NAME_RE.search(body)
    if m:
        results["item_name"] = m.group(1).strip()
    else:
        code = results.get("item_code") or ""
        all_items = re.findall(r"^\s*item\s*:\s*(.+?)\s*$", body, re.I | re.M)
        candidates = [v.strip() for v in all_items if v.strip() != code]
        results["item_name"] = candidates[0] if candidates else None

    return results


def skip_reason(fields: dict) -> str:
    """Determine why a record would be skipped."""
    if not fields.get("order_date") and not fields.get("customer_name"):
        return "❌ SKIP — both order_date AND customer_name are missing"
    return "✅ PARSED"


# ── Fetch emails ───────────────────────────────────────────────
print(f"\n{'═'*70}")
print(f"  DIAGNOSE SKIPPED EMAILS")
print(f"  Account : {GMAIL_ACCOUNT}")
print(f"  To      : {SUPPLIER_EMAIL}")
print(f"  Max     : {MAX_EMAILS} emails")
print(f"{'═'*70}\n")

days = max(1, math.ceil(8760 / 24))
query = f"to:{SUPPLIER_EMAIL} in:sent newer_than:{days}d"

listing = service.users().messages().list(
    userId=GMAIL_ACCOUNT, q=query
).execute()

refs = listing.get("messages", [])[:MAX_EMAILS]
print(f"📬 Found {len(refs)} message references\n")

# ── Analyse each email ─────────────────────────────────────────
skipped = []
parsed_count = 0

for i, ref in enumerate(refs, 1):
    msg_id = ref["id"]
    payload_data = service.users().messages().get(
        userId=GMAIL_ACCOUNT, id=msg_id, format="full"
    ).execute()

    body = decode_body(payload_data.get("payload", {}))
    fields = diagnose(body)
    reason = skip_reason(fields)

    is_skipped = reason.startswith("❌")

    if is_skipped:
        skipped.append({
            "index": i,
            "id": msg_id,
            "body": body,
            "fields": fields,
            "reason": reason,
        })
    else:
        parsed_count += 1

    # Progress dot
    sys.stdout.write("." if not is_skipped else "X")
    sys.stdout.flush()
    if i % 50 == 0:
        sys.stdout.write(f" {i}/{len(refs)}\n")
    time.sleep(0.05)  # gentle rate limit

print(f"\n\n{'─'*70}")
print(f"  RESULT: {parsed_count} parsed  |  {len(skipped)} skipped")
print(f"{'─'*70}\n")

# ── Print details for each skipped email ──────────────────────
if not skipped:
    print("🎉 No skipped emails found!")
    sys.exit(0)

print(f"{'═'*70}")
print(f"  SKIPPED EMAIL DETAILS ({len(skipped)} emails)")
print(f"{'═'*70}\n")

for s in skipped:
    body_preview = s["body"][:500].replace("\n", "↵ ") if s["body"] else "(EMPTY BODY)"
    found   = {k: v for k, v in s["fields"].items() if v}
    missing = [k for k, v in s["fields"].items() if not v]

    print(f"{'─'*70}")
    print(f"  Email #{s['index']}  ID: {s['id']}")
    print(f"  {s['reason']}")
    print()
    print(f"  FOUND fields   : {', '.join(f'{k}={repr(v)}' for k,v in found.items()) or 'none'}")
    print(f"  MISSING fields : {', '.join(missing) or 'none'}")
    print()
    print(f"  BODY PREVIEW:")
    # Print first 500 chars with line breaks preserved
    for line in s["body"].splitlines()[:20]:
        print(f"    {repr(line)}")
    if not s["body"]:
        print("    *** BODY IS EMPTY — may be HTML only or empty message ***")
    print()

# ── Summary table of missing fields across all skipped ─────────
print(f"{'═'*70}")
print("  MISSING FIELD FREQUENCY (across all skipped emails)")
print(f"{'─'*70}")
from collections import Counter
counter = Counter()
for s in skipped:
    for k, v in s["fields"].items():
        if not v:
            counter[k] += 1
for field, count in counter.most_common():
    bar = "█" * count
    print(f"  {field:<20} {count:>3}x  {bar}")
print(f"{'═'*70}\n")

"""FastAPI backend for the Order Automation System."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from datetime import date, datetime, timezone
from pathlib import Path

# ── Configure logging ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-22s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api")

# Load .env locally (in Cloud Run env vars are injected)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional


class AppendRequest(BaseModel):
    orders: Optional[List[dict]] = None  # frontend puede enviar orders directamente

from functions.email_parser import PARSER_REGISTRY, get_parser
from functions.gmail_client import GmailClient
from scripts.check_config import get_config_diagnostics

# ── Hardcoded business constants ──────────────────
STEPHEN_EMAIL = "7173783020@hellofax.com"
INBOX_ACCOUNT = "bettercrafter1@gmail.com"

# Gmail OAuth credentials (for webhook processing)
GMAIL_CLIENT_ID     = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "")

app = FastAPI(title="Order Automation System", version="1.0.0")

# CORS — allow local dev + Firebase Hosting URLs
_allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://orders-bf760.web.app",
    "https://orders-bf760.firebaseapp.com",
]
# Allow extra origins via env var (comma-separated)
_extra = os.environ.get("ALLOWED_ORIGINS", "")
if _extra:
    _allowed_origins.extend([o.strip() for o in _extra.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache for fetched orders (avoid re-fetching Gmail every time)
_cached_orders: list[dict] = []


def _get_gmail_client() -> GmailClient:
    logger.info("🔐 Authenticating with Gmail API...")
    client = GmailClient(
        gmail_account=os.environ.get("GMAIL_ACCOUNT", "bettercrafter1@gmail.com"),
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
    )
    logger.info("✅ Gmail API authenticated successfully")
    return client


def _is_valid_order(order: dict) -> bool:
    """Filter out orders without at least item_code + customer_name."""
    has_item     = bool(order.get("item_code", "").strip())
    has_customer = bool(order.get("customer_name", "").strip())
    return has_item and has_customer


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def normalize_parser_result(result) -> list[dict]:
    """Normalize parser output to a list of row dicts.

    Current parsers return list[dict] or None. Dict handling stays as a
    defensive bridge for older parser implementations.
    """
    if result is None:
        return []
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        rows: list[dict] = []
        for row in result:
            if isinstance(row, dict):
                rows.append(row)
            else:
                logger.warning("Ignoring non-dict parser row: %s", type(row).__name__)
        return rows

    logger.warning("Ignoring unsupported parser result type: %s", type(result).__name__)
    return []


def _clean_order_row(row: dict) -> dict:
    """Convert row values to stripped strings without mutating parser output."""
    return {str(key): "" if value is None else str(value).strip() for key, value in row.items()}


def _message_metadata(message, supplier_id: str, supplier_name: str, item_index: int) -> dict:
    """Build source metadata for an order row when available on the Gmail message."""
    metadata = {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "item_index": str(item_index),
    }

    for field, attr_names in {
        "message_id": ("message_id",),
        "thread_id": ("thread_id",),
        "email_subject": ("subject", "email_subject"),
        "email_date": ("email_date", "sent_date"),
    }.items():
        for attr_name in attr_names:
            value = getattr(message, attr_name, "")
            if value:
                metadata[field] = str(value).strip()
                break

    if "email_date" not in metadata:
        try:
            internal_date_ms = int(getattr(message, "internal_date_ms", 0) or 0)
        except (TypeError, ValueError):
            internal_date_ms = 0
        if internal_date_ms:
            metadata["email_date"] = datetime.fromtimestamp(
                internal_date_ms / 1000,
                tz=timezone.utc,
            ).date().isoformat()

    return metadata


def parse_message_to_order_rows(
    parser,
    message,
    supplier_id: str = "stephen",
    supplier_name: str = "Stephen",
) -> tuple[list[dict], int, int]:
    """Parse one Gmail message into valid order rows.

    Returns (valid_rows, invalid_rows, candidate_rows). Each parser row is
    validated independently so one bad item does not discard valid siblings.
    """
    raw_rows = normalize_parser_result(parser.parse(message.body, pdf_text=message.pdf_text or None))
    valid_rows: list[dict] = []
    invalid_rows = 0

    for item_index, raw_row in enumerate(raw_rows, start=1):
        order = _clean_order_row(raw_row)
        for key, value in _message_metadata(message, supplier_id, supplier_name, item_index).items():
            if value and not order.get(key):
                order[key] = value

        if _is_valid_order(order):
            valid_rows.append(order)
        else:
            invalid_rows += 1

    return valid_rows, invalid_rows, len(raw_rows)


def require_admin_api_key(
    x_admin_api_key: Optional[str] = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    """Temporary fail-closed guard for endpoints that mutate external state."""
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not expected_key or expected_key.lower().startswith("placeholder_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key is not configured",
        )
    if not x_admin_api_key or not secrets.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )


@app.get("/api/config-diagnostics", dependencies=[Depends(require_admin_api_key)])
def config_diagnostics():
    """Report environment key presence only; never expose configured values."""
    return get_config_diagnostics(os.environ)


@app.get("/api/orders-stream")
def fetch_orders_stream(start_date: str = None, end_date: str = None):
    """SSE endpoint — streams progress events while fetching/parsing emails.
    start_date and end_date are ISO strings like '2025-07-11'
    """

    def event_generator():
        global _cached_orders
        t0 = time.time()

        # Step 1: Auth
        yield _sse_event("progress", {"step": "auth", "message": "🔐 Authenticating with Gmail API...", "percent": 5})
        try:
            gmail = _get_gmail_client()
        except Exception as e:
            yield _sse_event("error", {"message": f"Auth failed: {e}"})
            return

        # Step 2: Fetch email list
        yield _sse_event("progress", {"step": "fetch_list", "message": "📨 Fetching email list from Gmail...", "percent": 10})
        supplier_email = STEPHEN_EMAIL  # hardcoded constant — no env var needed
        logger.info("🎯 Target supplier (hardcoded): %s", supplier_email)
        logger.info("📅 Date range: %s → %s", start_date or "(no start)", end_date or "(no end)")
        try:
            messages = gmail.list_supplier_messages(
                supplier_email=supplier_email,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as e:
            yield _sse_event("error", {"message": f"Failed to fetch emails: {e}"})
            return

        total = len(messages)
        logger.info("📬 Found %d emails from %s", total, supplier_email)
        yield _sse_event("progress", {"step": "fetched", "message": f"📬 Found {total} emails", "percent": 20, "total": total})

        # Step 3: Initialize parser
        using_gemini = bool(os.environ.get("GEMINI_API_KEY"))
        yield _sse_event("progress", {"step": "parser_init", "message": "🧠 Initializing parser...", "percent": 25})
        parser = get_parser("stephen")

        # Step 4: Parse emails one by one
        orders: list[dict] = []
        failed = 0
        invalid_rows_total = 0
        empty_parser_results = 0
        pdf_count = 0

        for i, msg in enumerate(messages):
            idx = i + 1
            has_pdf = bool(msg.pdf_text)
            if has_pdf:
                pdf_count += 1

            logger.info("  🔍 [%d/%d] msg_id=%s body=%d chars pdf=%d chars files=%s",
                        idx, total, msg.message_id[:10], len(msg.body),
                        len(msg.pdf_text or ""), msg.pdf_filenames or [])

            valid_rows, invalid_rows, candidate_rows = parse_message_to_order_rows(parser, msg)
            invalid_rows_total += invalid_rows
            failed += invalid_rows
            if valid_rows:
                orders.extend(valid_rows)
                customer = valid_rows[0].get('customer_name', '?')
                item = valid_rows[0].get('item_code', '?')
                logger.info(
                    "  ✅ [%d/%d] Parsed %d row(s) — customer=%s, first item=%s%s",
                    idx, total, len(valid_rows), customer, item, " 📎PDF" if has_pdf else ""
                )
            else:
                if candidate_rows == 0:
                    empty_parser_results += 1
                    failed += 1
                logger.info(
                    "  ❌ [%d/%d] Skipped — parser rows=%d invalid rows=%d",
                    idx, total, candidate_rows, invalid_rows,
                )

            # Send progress every email
            pct = 25 + int((idx / total) * 65)  # 25% → 90%
            yield _sse_event("progress", {
                "step": "parsing",
                "message": f"🔍 Parsing email {idx}/{total}{'  📎PDF' if has_pdf else ''}",
                "percent": pct,
                "current": idx,
                "total": total,
                "parsed": len(orders),
                "orders_parsed": len(orders),
                "failed": failed,
                "invalid_rows": invalid_rows_total,
                "empty_parser_results": empty_parser_results,
                "pdfs": pdf_count,
            })

        _cached_orders = orders
        elapsed = round(time.time() - t0, 1)

        logger.info("═" * 50)
        logger.info("📊 RESULTS: %d parsed, %d skipped, %d PDFs — %.1fs", len(orders), failed, pdf_count, elapsed)
        logger.info("═" * 50)

        # Step 5: Done
        yield _sse_event("complete", {
            "message": f"✅ Done in {elapsed}s",
            "percent": 100,
            "emails_found": total,
            "total_emails": total,
            "parsed": len(orders),
            "orders_parsed": len(orders),
            "failed": failed,
            "invalid_rows": invalid_rows_total,
            "empty_parser_results": empty_parser_results,
            "pdfs_found": pdf_count,
            "elapsed": elapsed,
            "orders": orders,
        })

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/orders")
def fetch_orders(start_date: str = None, end_date: str = None):
    """Fetch and parse real supplier emails from Gmail (non-streaming)."""
    global _cached_orders
    t0 = time.time()
    try:
        logger.info("═" * 50)
        logger.info("🚀 Starting order fetch start=%s end=%s", start_date, end_date)
        logger.info("═" * 50)

        gmail = _get_gmail_client()
        parser = get_parser("stephen")
        supplier_email = STEPHEN_EMAIL  # hardcoded constant — no env var needed

        logger.info("🎯 Target supplier (hardcoded): %s", supplier_email)
        logger.info("📅 Date range: %s → %s", start_date or "(no start)", end_date or "(no end)")
        messages = gmail.list_supplier_messages(
            supplier_email=supplier_email,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("📬 Found %d emails", len(messages))

        orders: list[dict] = []
        failed = 0
        invalid_rows_total = 0
        empty_parser_results = 0
        pdf_count = 0
        for i, msg in enumerate(messages):
            has_pdf = bool(msg.pdf_text)
            if has_pdf:
                pdf_count += 1
            valid_rows, invalid_rows, candidate_rows = parse_message_to_order_rows(parser, msg)
            invalid_rows_total += invalid_rows
            failed += invalid_rows
            if valid_rows:
                orders.extend(valid_rows)
                logger.info(
                    "  ✅ [%d/%d] %d row(s) — %s — %s%s",
                    i + 1, len(messages),
                    len(valid_rows),
                    valid_rows[0].get('customer_name', '?'),
                    valid_rows[0].get('item_code', '?'),
                    " 📎" if has_pdf else "",
                )
            else:
                if candidate_rows == 0:
                    empty_parser_results += 1
                    failed += 1
                logger.info(
                    "  ❌ [%d/%d] Skipped — parser rows=%d invalid rows=%d",
                    i + 1, len(messages), candidate_rows, invalid_rows,
                )

        _cached_orders = orders
        elapsed = round(time.time() - t0, 1)

        logger.info("═" * 50)
        logger.info("📊 DONE: %d parsed, %d skipped, %d PDFs — %.1fs", len(orders), failed, pdf_count, elapsed)
        logger.info("═" * 50)

        return {
            "emails_found": len(messages),
            "total_emails": len(messages),
            "parsed": len(orders),
            "orders_parsed": len(orders),
            "failed": failed,
            "invalid_rows": invalid_rows_total,
            "empty_parser_results": empty_parser_results,
            "pdfs_found": pdf_count,
            "elapsed": elapsed,
            "orders": orders,
        }
    except Exception as e:
        logger.error("💥 Error fetching orders: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/append-to-onedrive", dependencies=[Depends(require_admin_api_key)])
def append_to_onedrive(body: AppendRequest = None):
    """Append parsed orders to the existing OneDrive Word document.

    Downloads the live .docx from OneDrive, appends new order rows (skipping
    duplicates), and uploads it back.
    """
    try:
        from functions.onedrive_client import download_docx, upload_docx, get_file_name
        from functions.word_generator import append_orders_to_existing_docx
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"OneDrive module not available: {e}")

    orders_to_use = (body.orders if body and body.orders else None) or _cached_orders
    if not orders_to_use:
        raise HTTPException(status_code=400, detail="No orders loaded. Fetch orders first.")

    try:
        file_name = get_file_name()
        logger.info("📥 Downloading '%s' from OneDrive...", file_name)
        docx_bytes = download_docx()

        logger.info("✏️  Processing %d order(s)...", len(orders_to_use))
        updated_bytes, appended, skipped = append_orders_to_existing_docx(docx_bytes, orders_to_use)

        if appended == 0:
            logger.info("⏭️  All %d orders already in file — nothing to upload", skipped)
            return {
                "success": True,
                "file_name": file_name,
                "orders_appended": 0,
                "orders_skipped": skipped,
                "message": f"All {skipped} order(s) already exist in the file — no changes made.",
            }

        logger.info("📤 Uploading updated document back to OneDrive...")
        upload_docx(updated_bytes)

        logger.info("✅ OneDrive updated: %s (+%d rows, %d skipped)", file_name, appended, skipped)
        return {
            "success": True,
            "file_name": file_name,
            "orders_appended": appended,
            "orders_skipped": skipped,
        }
    except Exception as e:
        logger.error("💥 OneDrive append failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/gmail-webhook", status_code=200, dependencies=[Depends(require_admin_api_key)])
async def gmail_webhook(request: Request):
    """Receive Gmail push notifications from Google Pub/Sub."""
    import base64
    import json as _json

    # Log everything about the incoming request
    headers = dict(request.headers)
    raw = await request.body()
    logger.info("═" * 50)
    logger.info("📩 WEBHOOK HIT — method=%s url=%s", request.method, request.url)
    logger.info("📩 Headers: %s", {k: v for k, v in headers.items() if k.lower() in ('content-type','content-length','user-agent')})
    logger.info("📩 Body (%d bytes): %s", len(raw), raw[:500])

    try:
        body = _json.loads(raw)
    except Exception as e:
        logger.error("❌ Could not parse webhook body as JSON: %s — raw=%s", e, raw[:200])
        return {"status": "ok"}  # Return 200 so Pub/Sub stops retrying

    # Pub/Sub wraps the payload in message.data (base64-encoded)
    encoded = body.get("message", {}).get("data", "")
    if not encoded:
        logger.warning("⚠️  No message.data in webhook body: %s", body)
        return {"status": "no_data"}

    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        notification = _json.loads(decoded)
    except Exception as e:
        logger.error("Failed to decode Pub/Sub message: %s", e)
        return {"status": "ok"}  # Return 200 so Pub/Sub stops retrying

    email_address = notification.get("emailAddress", "")
    history_id    = notification.get("historyId", "")
    logger.info("═" * 50)
    logger.info("📬 WEBHOOK RECEIVED — account=%s historyId=%s", email_address, history_id)
    logger.info("═" * 50)

    # Only process if we have Gmail credentials
    if not GMAIL_REFRESH_TOKEN:
        logger.warning("⚠️  GMAIL_REFRESH_TOKEN not set — skipping webhook processing")
        return {"status": "skipped", "reason": "no_credentials"}

    try:
        from datetime import date as _date, timedelta
        from functions.email_parser import get_parser
        from functions.onedrive_client import download_docx, upload_docx
        from functions.word_generator import append_orders_to_existing_docx

        logger.info("🔐 Authenticating Gmail for account=%s...", INBOX_ACCOUNT)
        gmail = GmailClient(
            gmail_account=INBOX_ACCOUNT,
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            refresh_token=GMAIL_REFRESH_TOKEN,
        )
        parser = get_parser("stephen")

        # Fetch today's emails first
        today_str = _date.today().isoformat()
        logger.info("📨 Fetching emails from Stephen (%s) since today (%s)...", STEPHEN_EMAIL, today_str)
        messages = gmail.list_supplier_messages(
            supplier_email=STEPHEN_EMAIL,
            start_date=today_str,
            end_date=None,
        )
        logger.info("📬 Found %d email(s) from Stephen today", len(messages))

        # If nothing today, fetch last 7 days as safety net
        if len(messages) == 0:
            logger.info("📨 No emails today — fetching last 7 days as catch-up...")
            week_ago = (_date.today() - timedelta(days=7)).isoformat()
            messages = gmail.list_supplier_messages(
                supplier_email=STEPHEN_EMAIL,
                start_date=week_ago,
                end_date=None,
            )
            logger.info("📬 Found %d email(s) from last 7 days", len(messages))

        new_orders = []
        invalid_rows_total = 0
        empty_parser_results = 0
        for msg in messages:
            logger.info("  🔍 Parsing msg_id=%s (body=%d chars, pdf=%d chars)",
                        msg.message_id[:12], len(msg.body), len(msg.pdf_text or ""))
            valid_rows, invalid_rows, candidate_rows = parse_message_to_order_rows(parser, msg)
            invalid_rows_total += invalid_rows
            if not valid_rows:
                if candidate_rows == 0:
                    empty_parser_results += 1
                logger.warning(
                    "  ❌ msg_id=%s — no valid order parsed (parser rows=%d invalid rows=%d)",
                    msg.message_id[:12], candidate_rows, invalid_rows,
                )
                continue
            for order in valid_rows:
                logger.info("  ✅ msg_id=%s → customer=%s item=%s date=%s",
                            msg.message_id[:12], order.get("customer_name"), order.get("item_code"), order.get("order_date"))
            new_orders.extend(valid_rows)

        if not new_orders:
            logger.info("ℹ️  No parseable orders found — nothing to append to OneDrive")
            return {
                "status": "ok",
                "orders_found": 0,
                "invalid_rows": invalid_rows_total,
                "empty_parser_results": empty_parser_results,
            }

        logger.info("📥 Downloading OneDrive document...")
        docx_bytes = download_docx()
        logger.info("✏️  Appending %d order(s) — duplicates will be skipped automatically...", len(new_orders))
        updated, appended, skipped = append_orders_to_existing_docx(docx_bytes, new_orders)

        if appended > 0:
            logger.info("📤 Uploading updated document to OneDrive...")
            upload_docx(updated)
            logger.info("✅ OneDrive updated: +%d rows appended, %d duplicates skipped", appended, skipped)
        else:
            logger.info("⏭️  All %d orders already in OneDrive — no upload needed", skipped)

        logger.info("═" * 50)
        logger.info("🏁 WEBHOOK DONE — appended=%d skipped=%d", appended, skipped)
        logger.info("═" * 50)
        return {
            "status": "ok",
            "orders_appended": appended,
            "orders_skipped": skipped,
            "invalid_rows": invalid_rows_total,
            "empty_parser_results": empty_parser_results,
        }

    except Exception as e:
        logger.error("═" * 50)
        logger.error("💥 WEBHOOK FAILED: %s", e, exc_info=True)
        logger.error("═" * 50)
        # Return 200 so Pub/Sub doesn't keep retrying on parse errors
        return {"status": "error", "detail": str(e)}


@app.post("/api/clear-onedrive-rows", dependencies=[Depends(require_admin_api_key)])
def clear_onedrive_rows(
    start_date: str = Query(default=None, description="Fecha inicio MM/DD/YYYY — omitir para borrar todo"),
    end_date:   str = Query(default=None, description="Fecha fin   MM/DD/YYYY — omitir para borrar todo"),
):
    """Borra filas de datos del documento OneDrive en el rango de fechas dado.

    Ejemplos:
      Borrar todo:            POST /api/clear-onedrive-rows
      Solo un mes:            POST /api/clear-onedrive-rows?start_date=04/14/2026&end_date=05/04/2026

    El header del documento siempre se preserva.
    Después de llamar este endpoint, usar /api/daily-update?days=N para reescribir en orden correcto.
    """
    try:
        from functions.onedrive_client import download_docx, upload_docx, get_file_name
        from functions.word_generator import clear_rows_from_docx

        file_name = get_file_name()
        logger.info("═" * 50)
        logger.info("🗑️  CLEAR ROWS — file=%s range=%s → %s", file_name, start_date or "*", end_date or "*")
        logger.info("═" * 50)

        docx_bytes = download_docx()
        updated_bytes, deleted = clear_rows_from_docx(docx_bytes, start_date=start_date, end_date=end_date)

        if deleted == 0:
            logger.info("ℹ️  No rows matched the date range — nothing deleted")
            return {"status": "ok", "rows_deleted": 0, "message": "No rows matched"}

        upload_docx(updated_bytes)
        logger.info("✅ Deleted %d rows and uploaded updated document", deleted)
        return {
            "status": "ok",
            "rows_deleted": deleted,
            "range": f"{start_date or '*'} → {end_date or '*'}",
        }
    except Exception as e:
        logger.error("💥 clear-onedrive-rows failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/daily-update", dependencies=[Depends(require_admin_api_key)])
def daily_update(days: int = Query(default=2, ge=1, le=30, description="Cuántos días hacia atrás procesar")):
    """Fetch emails from the last N days and append them to OneDrive.

    - Llamado por Cloud Scheduler a las 2 AM (days=1 → solo ayer)
    - Llamado manualmente para catch-up (days=2, 7, etc.)
    Funciona en la madrugada cuando Leo tiene el archivo cerrado → sin 423 Locked.
    """
    if not GMAIL_REFRESH_TOKEN:
        raise HTTPException(status_code=503, detail="GMAIL_REFRESH_TOKEN not set")

    try:
        from datetime import timedelta
        from functions.email_parser import get_parser as _get_parser
        from functions.onedrive_client import download_docx, upload_docx, get_file_name
        from functions.word_generator import append_orders_to_existing_docx

        start_date = (date.today() - timedelta(days=days)).isoformat()
        end_date   = date.today().isoformat()

        logger.info("═" * 50)
        logger.info("🌙 DAILY UPDATE — last %d day(s): %s → %s", days, start_date, end_date)
        logger.info("═" * 50)

        gmail = GmailClient(
            gmail_account=INBOX_ACCOUNT,
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            refresh_token=GMAIL_REFRESH_TOKEN,
        )
        parser = _get_parser("stephen")

        messages = gmail.list_supplier_messages(
            supplier_email=STEPHEN_EMAIL,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("📬 Found %d email(s) from Stephen in range %s → %s", len(messages), start_date, end_date)

        orders: list[dict] = []
        invalid_rows_total = 0
        empty_parser_results = 0
        for msg in messages:
            valid_rows, invalid_rows, candidate_rows = parse_message_to_order_rows(parser, msg)
            invalid_rows_total += invalid_rows
            if valid_rows:
                orders.extend(valid_rows)
                for order in valid_rows:
                    logger.info("  ✅ customer=%s item=%s", order.get("customer_name"), order.get("item_code"))
            else:
                if candidate_rows == 0:
                    empty_parser_results += 1
                logger.info(
                    "  ❌ msg_id=%s — skipped (parser rows=%d invalid rows=%d)",
                    msg.message_id[:12], candidate_rows, invalid_rows,
                )

        if not orders:
            logger.info("ℹ️  No valid orders found in range — nothing to append")
            return {
                "status": "ok",
                "range": f"{start_date} → {end_date}",
                "emails_found": len(messages),
                "orders_found": 0,
                "orders_appended": 0,
                "invalid_rows": invalid_rows_total,
                "empty_parser_results": empty_parser_results,
                "message": "No orders found in date range",
            }

        file_name = get_file_name()
        logger.info("📥 Downloading '%s' from OneDrive...", file_name)
        docx_bytes = download_docx()

        logger.info("✏️  Appending %d order(s) — duplicates skipped automatically...", len(orders))
        updated, appended, skipped = append_orders_to_existing_docx(docx_bytes, orders)

        if appended > 0:
            logger.info("📤 Uploading updated document to OneDrive...")
            upload_docx(updated)
            logger.info("✅ Update done: +%d rows (%d duplicates skipped)", appended, skipped)
        else:
            logger.info("⏭️  All %d orders already in OneDrive — no upload needed", skipped)

        logger.info("═" * 50)
        logger.info("🏁 DAILY UPDATE DONE — range=%s→%s appended=%d skipped=%d", start_date, end_date, appended, skipped)
        logger.info("═" * 50)
        return {
            "status": "ok",
            "range": f"{start_date} → {end_date}",
            "emails_found": len(messages),
            "orders_found": len(orders),
            "orders_appended": appended,
            "orders_skipped": skipped,
            "invalid_rows": invalid_rows_total,
            "empty_parser_results": empty_parser_results,
        }
    except Exception as e:
        logger.error("💥 Daily update failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/renew-gmail-watch", dependencies=[Depends(require_admin_api_key)])
def renew_gmail_watch():
    """Renew the Gmail push notification watch (expires every 7 days).
    Call this from Cloud Scheduler once a day.
    """
    if not GMAIL_REFRESH_TOKEN:
        raise HTTPException(status_code=503, detail="GMAIL_REFRESH_TOKEN not set")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build as _build

        GCP_PROJECT  = os.environ.get("GCP_PROJECT", "ordersbc-494213")
        PUBSUB_TOPIC = f"projects/{GCP_PROJECT}/topics/gmail-orders"

        creds = Credentials(
            token=None,
            refresh_token=GMAIL_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        creds.refresh(Request())
        svc = _build("gmail", "v1", credentials=creds, cache_discovery=False)
        resp = svc.users().watch(
            userId=INBOX_ACCOUNT,
            body={"topicName": PUBSUB_TOPIC, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"},
        ).execute()
        logger.info("✅ Gmail watch renewed — historyId=%s expiration=%s", resp.get("historyId"), resp.get("expiration"))
        return {"status": "ok", "historyId": resp.get("historyId"), "expiration": resp.get("expiration")}
    except Exception as e:
        logger.error("💥 Failed to renew Gmail watch: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "date": date.today().isoformat()}


# ── Serve frontend static files (built by Vite in Docker stage 1) ──
_frontend_dir = Path(__file__).parent / "frontend_dist"
if _frontend_dir.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse as _FR

    # Mount Vite's /assets directory
    app.mount("/assets", StaticFiles(directory=str(_frontend_dir / "assets")), name="assets")

    @app.get("/")
    def _serve_index():
        return _FR(str(_frontend_dir / "index.html"))

    @app.get("/{full_path:path}")
    def _serve_spa(full_path: str):
        # Serve actual file if exists, else fallback to index.html (SPA routing)
        file_path = _frontend_dir / full_path
        if file_path.is_file():
            return _FR(str(file_path))
        return _FR(str(_frontend_dir / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

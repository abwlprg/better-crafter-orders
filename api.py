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
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional


class AppendRequest(BaseModel):
    orders: Optional[List[dict]] = None  # frontend puede enviar orders directamente


class BatchOrdersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_ids: List[str] = Field(..., min_length=1)
    start_date: str
    end_date: str
    dry_run: bool = True
    write_target: str = "none"
    include_orders: bool = False
    max_preview_rows: int = Field(default=100, ge=0)

    @field_validator("supplier_ids")
    @classmethod
    def supplier_ids_must_be_non_empty(cls, value: List[str]) -> List[str]:
        supplier_ids = [
            supplier_id.strip().lower()
            for supplier_id in value
            if supplier_id.strip()
        ]
        if not supplier_ids:
            raise ValueError("supplier_ids must include at least one supplier")
        return supplier_ids

    @field_validator("start_date", "end_date")
    @classmethod
    def dates_must_be_iso_yyyy_mm_dd(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError("date must use YYYY-MM-DD format")
        if parsed.isoformat() != value:
            raise ValueError("date must use YYYY-MM-DD format")
        return value

    @field_validator("write_target")
    @classmethod
    def write_target_must_be_valid(cls, value: str) -> str:
        if value not in ("none", "sandbox"):
            raise ValueError("write_target must be 'none' or 'sandbox'")
        return value


class SupplierCreateRequest(BaseModel):
    id: str
    name: str
    email: str = ""
    status: str = "active"
    onedrive_file_name: str = ""
    onedrive_file_id: str = ""
    onedrive_drive_id: str = ""
    parser_type: str = "stephen_regex"
    custom_fields: List[dict] = Field(default_factory=list)
    word_schema: Optional[dict] = None


class SupplierUpdateRequest(BaseModel):
    name: str
    email: str = ""
    status: str = "active"
    onedrive_file_name: str = ""
    onedrive_file_id: str = ""
    onedrive_drive_id: str = ""
    parser_type: str = "stephen_regex"
    custom_fields: List[dict] = Field(default_factory=list)
    word_schema: Optional[dict] = None


class SupplierPatchRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    onedrive_file_name: Optional[str] = None
    onedrive_file_id: Optional[str] = None
    onedrive_drive_id: Optional[str] = None
    parser_type: Optional[str] = None
    custom_fields: Optional[List[dict]] = None
    word_schema: Optional[dict] = None


from functions.email_parser import PARSER_REGISTRY, get_parser
from functions.gmail_client import GmailClient
from functions import supplier_config as _supplier_config
from functions import run_log as _run_log
from scripts.check_config import get_config_diagnostics

# ── Hardcoded business constants ──────────────────
STEPHEN_EMAIL = "7173783020@hellofax.com"
INBOX_ACCOUNT = "bettercrafter1@gmail.com"
MAX_BATCH_PREVIEW_ROWS = 100
SUPPORTED_BATCH_SUPPLIERS = {
    "stephen": {
        "supplier_id": "stephen",
        "supplier_name": "Stephen",
        "supplier_email": STEPHEN_EMAIL,
        "parser_key": "stephen",
    },
    "steven": {
        "supplier_id": "steven",
        "supplier_name": "Stephen",
        "supplier_email": STEPHEN_EMAIL,
        "parser_key": "stephen",
    },
}
PREVIEW_ORDER_FIELDS = (
    "order_date",
    "item_code",
    "item_name",
    "color",
    "ship_by",
    "customer_name",
    "quantity",
    "brand",
    "supplier_id",
    "supplier_name",
    "item_index",
    "message_id",
    "thread_id",
    "email_subject",
    "email_date",
)

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


def _sanitize_preview_order(row: dict) -> dict:
    """Return only business-safe preview fields from a parsed order row."""
    return {field: row[field] for field in PREVIEW_ORDER_FIELDS if field in row}


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


@app.post("/api/batch-orders", dependencies=[Depends(require_admin_api_key)])
def batch_orders(body: BatchOrdersRequest):
    """Admin-protected read-only batch preview for supplier order candidates."""
    if not body.dry_run:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dry_run=false is not supported for /api/batch-orders",
        )

    unsupported = [
        supplier_id
        for supplier_id in body.supplier_ids
        if supplier_id not in SUPPORTED_BATCH_SUPPLIERS
    ]
    # Build a merged supplier map: hardcoded fallback + configured suppliers
    _config_suppliers = {
        s["id"]: {
            "supplier_id": s["id"],
            "supplier_name": s["name"],
            "supplier_email": s.get("email", ""),
            "parser_key": "stephen" if s.get("parser_type") in ("stephen_regex", None) else "stephen",
        }
        for s in _supplier_config.get_all()
        if s.get("email", "").strip()
    }
    _all_suppliers = {**_config_suppliers, **SUPPORTED_BATCH_SUPPLIERS}

    unsupported = [sid for sid in body.supplier_ids if sid not in _all_suppliers]
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Unsupported supplier_id requested",
                "unsupported_supplier_ids": unsupported,
                "supported_supplier_ids": sorted(_all_suppliers),
            },
        )

    preview_limit = min(body.max_preview_rows, MAX_BATCH_PREVIEW_ROWS)
    gmail = _get_gmail_client()
    suppliers = []

    logger.info(
        "Batch dry-run preview requested suppliers=%s range=%s to %s include_orders=%s cap=%d",
        body.supplier_ids,
        body.start_date,
        body.end_date,
        body.include_orders,
        preview_limit,
    )

    for supplier_id in body.supplier_ids:
        supplier = _all_suppliers[supplier_id]
        supplier_errors: list[str] = []
        orders: list[dict] = []
        invalid_rows_total = 0
        orders_parsed = 0
        emails_found = 0

        try:
            messages = gmail.list_supplier_messages(
                supplier_email=supplier["supplier_email"],
                start_date=body.start_date,
                end_date=body.end_date,
            )
            emails_found = len(messages)
            parser = get_parser(supplier["parser_key"])

            for message in messages:
                valid_rows, invalid_rows, candidate_rows = parse_message_to_order_rows(
                    parser,
                    message,
                    supplier_id=supplier["supplier_id"],
                    supplier_name=supplier["supplier_name"],
                )
                invalid_rows_total += invalid_rows
                orders_parsed += len(valid_rows)
                if candidate_rows == 0:
                    supplier_errors.append(
                        f"No parser rows for message {getattr(message, 'message_id', '')}"
                    )
                if body.include_orders and len(orders) < preview_limit:
                    remaining = preview_limit - len(orders)
                    orders.extend(
                        _sanitize_preview_order(row) for row in valid_rows[:remaining]
                    )
        except Exception as exc:
            logger.error(
                "Batch dry-run supplier=%s failed: %s",
                supplier_id,
                exc,
                exc_info=True,
            )
            supplier_errors.append(str(exc))

        would_append = orders_parsed
        summary = {
            "supplier_id": supplier["supplier_id"],
            "supplier_name": supplier["supplier_name"],
            "emails_found": emails_found,
            "orders_parsed": orders_parsed,
            "invalid_rows": invalid_rows_total,
            "duplicates": None,
            "would_append": would_append,
            "appended": 0,
            "errors": supplier_errors,
            "orders": orders if body.include_orders else [],
        }
        suppliers.append(summary)

        logger.info(
            "Batch dry-run supplier=%s emails=%d parsed=%d invalid=%d would_append=%d errors=%d",
            supplier_id,
            emails_found,
            orders_parsed,
            invalid_rows_total,
            would_append,
            len(supplier_errors),
        )

    total_parsed = sum(s["orders_parsed"] for s in suppliers)
    total_emails = sum(s["emails_found"] for s in suppliers)
    any_errors = any(s["errors"] for s in suppliers)
    try:
        _run_log.append_entry(
            supplier_ids=body.supplier_ids,
            start_date=body.start_date,
            end_date=body.end_date,
            emails_found=total_emails,
            orders_parsed=total_parsed,
            orders_written=0,
            orders_skipped=0,
            dry_run=True,
            status="error" if any_errors else "ok",
        )
    except Exception as _log_exc:
        logger.warning("Failed to write run log: %s", _log_exc)

    return {
        "status": "ok",
        "dry_run": True,
        "range": {
            "start_date": body.start_date,
            "end_date": body.end_date,
        },
        "suppliers": suppliers,
    }


@app.get("/api/orders-stream", dependencies=[Depends(require_admin_api_key)])
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


@app.get("/api/orders", dependencies=[Depends(require_admin_api_key)])
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


@app.get("/api/config-status", dependencies=[Depends(require_admin_api_key)])
def config_status():
    """Admin-only endpoint — returns booleans/status labels about configured services, never raw values."""
    def _has(key: str) -> bool:
        val = os.environ.get(key, "").strip()
        return bool(val) and not val.lower().startswith("placeholder")

    def _legacy_status(key: str) -> bool | str:
        val = os.environ.get(key, "").strip()
        if not val:
            return False
        if val.lower().startswith("placeholder"):
            return "placeholder"
        return True

    sandbox_write_raw = os.environ.get("ONEDRIVE_SANDBOX_WRITE_ENABLED", "").strip().lower()
    gemini_key_present = _has("GEMINI_API_KEY")

    return {
        "local": {
            "gcp_project": _has("GCP_PROJECT"),
            "allowed_origins": _has("ALLOWED_ORIGINS"),
        },
        "admin_api_key": _has("ADMIN_API_KEY"),
        "gmail": {
            "account": _has("GMAIL_ACCOUNT"),
            "client_id": _has("GMAIL_CLIENT_ID"),
            "client_secret": _has("GMAIL_CLIENT_SECRET"),
            "refresh_token": _has("GMAIL_REFRESH_TOKEN"),
        },
        "onedrive": {
            "client_id": _has("MS_CLIENT_ID"),
            "tenant_id": _has("MS_TENANT_ID"),
            "refresh_token": _has("MS_REFRESH_TOKEN"),
            "sandbox_drive_id": _has("ONEDRIVE_TEST_DRIVE_ID"),
            "sandbox_file_id": _has("ONEDRIVE_TEST_FILE_ID"),
            "sandbox_write_enabled": sandbox_write_raw == "true",
        },
        "production_later": {
            "production_drive_id": _has("ONEDRIVE_DRIVE_ID"),
            "production_file_id": _has("ONEDRIVE_FILE_ID"),
        },
        "legacy_reference": {
            "storage_bucket": _legacy_status("STORAGE_BUCKET"),
            "firestore_collection": _legacy_status("FIRESTORE_COLLECTION"),
            "search_hours_back": _legacy_status("SEARCH_HOURS_BACK"),
            "report_prefix": _legacy_status("REPORT_PREFIX"),
            "template_path": _legacy_status("TEMPLATE_PATH"),
        },
        "gemini": {
            "api_key": gemini_key_present,
            "enabled": False,
            "reason": "billing_or_quota_not_confirmed",
        },
    }


# ── Supplier CRUD ──────────────────────────────────────────────────────────────

@app.get("/api/suppliers", dependencies=[Depends(require_admin_api_key)])
def list_suppliers():
    return {"suppliers": _supplier_config.get_all()}


@app.post("/api/suppliers", status_code=201, dependencies=[Depends(require_admin_api_key)])
def create_supplier(body: SupplierCreateRequest):
    try:
        supplier = _supplier_config.create(body.model_dump())
        return {"supplier": supplier}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.put("/api/suppliers/{supplier_id}", dependencies=[Depends(require_admin_api_key)])
def replace_supplier(supplier_id: str, body: SupplierUpdateRequest):
    try:
        supplier = _supplier_config.update(supplier_id, body.model_dump())
        return {"supplier": supplier}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.patch("/api/suppliers/{supplier_id}", dependencies=[Depends(require_admin_api_key)])
def patch_supplier(supplier_id: str, body: SupplierPatchRequest):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        supplier = _supplier_config.patch(supplier_id, updates)
        return {"supplier": supplier}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.delete("/api/suppliers/{supplier_id}", dependencies=[Depends(require_admin_api_key)])
def delete_supplier(supplier_id: str):
    """Delete a supplier from the app and attempt to remove its associated OneDrive files.

    Sandbox deletion: uses sandbox_onedrive_drive_id / sandbox_onedrive_file_id.
        Requires ONEDRIVE_SANDBOX_WRITE_ENABLED=true.
    Production deletion: uses onedrive_drive_id / onedrive_file_id.
        Requires ONEDRIVE_PRODUCTION_DELETE_ENABLED=true (blocked by default).
    The supplier is always removed from the app regardless of OneDrive outcome.
    """
    from functions.onedrive_client import delete_item as _delete_item

    supplier = _supplier_config.get_by_id(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail=f"Supplier '{supplier_id}' not found")

    warnings: list[str] = []
    onedrive_attempted = False
    onedrive_deleted   = False
    sandbox_deleted    = False

    # ── Sandbox document deletion ──────────────────────────────────────────────
    sb_drive_id = supplier.get("sandbox_onedrive_drive_id", "").strip()
    sb_file_id  = supplier.get("sandbox_onedrive_file_id",  "").strip()

    if sb_drive_id and sb_file_id:
        sb_write_ok = (
            os.environ.get("ONEDRIVE_SANDBOX_WRITE_ENABLED", "").strip().lower() == "true"
        )
        if not sb_write_ok:
            warnings.append(
                "Sandbox doc deletion skipped: ONEDRIVE_SANDBOX_WRITE_ENABLED is not true."
            )
        else:
            onedrive_attempted = True
            try:
                _delete_item(sb_drive_id, sb_file_id)
                onedrive_deleted = True
                sandbox_deleted  = True
            except FileNotFoundError:
                warnings.append(
                    "Sandbox OneDrive file was already missing — supplier still removed."
                )
            except Exception as exc:
                logger.error(
                    "Sandbox delete failed for supplier=%s: %s", supplier_id, exc, exc_info=True
                )
                warnings.append(f"Sandbox OneDrive deletion failed: {str(exc)[:200]}")

    # ── Production document deletion (blocked unless explicitly enabled) ────────
    prod_file_id  = supplier.get("onedrive_file_id",  "").strip()
    prod_drive_id = supplier.get("onedrive_drive_id", "").strip()

    if prod_file_id and prod_drive_id:
        prod_delete_ok = (
            os.environ.get("ONEDRIVE_PRODUCTION_DELETE_ENABLED", "").strip().lower() == "true"
        )
        if not prod_delete_ok:
            warnings.append(
                "Production doc deletion skipped: ONEDRIVE_PRODUCTION_DELETE_ENABLED is not true."
            )
        else:
            onedrive_attempted = True
            try:
                _delete_item(prod_drive_id, prod_file_id)
                onedrive_deleted = True
            except FileNotFoundError:
                warnings.append("Production OneDrive file was already missing.")
            except Exception as exc:
                logger.error(
                    "Production delete failed for supplier=%s: %s", supplier_id, exc, exc_info=True
                )
                warnings.append(f"Production OneDrive deletion failed: {str(exc)[:200]}")

    if not sb_drive_id and not prod_drive_id:
        warnings.append("No OneDrive file metadata on this supplier — removed from app only.")

    # Delete from app regardless of OneDrive outcome
    app_deleted = False
    try:
        _supplier_config.delete(supplier_id)
        app_deleted = True
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        _run_log.append_delete_entry(
            supplier_id=supplier_id,
            app_supplier_deleted=app_deleted,
            onedrive_delete_attempted=onedrive_attempted,
            onedrive_deleted=onedrive_deleted,
            warnings=warnings,
        )
    except Exception as _log_exc:
        logger.warning("Failed to write delete run log: %s", _log_exc)

    return {
        "status": "ok",
        "supplier_id": supplier_id,
        "app_supplier_deleted": app_deleted,
        "onedrive_delete_attempted": onedrive_attempted,
        "onedrive_deleted": onedrive_deleted,
        "sandbox_deleted": sandbox_deleted,
        "warnings": warnings,
    }


@app.post("/api/suppliers/{supplier_id}/create-sandbox-docx", dependencies=[Depends(require_admin_api_key)])
def create_or_update_supplier_sandbox_docx(supplier_id: str):
    """Idempotent sandbox document create/update.

    - No sandbox metadata on supplier → create new doc, store metadata.
    - Sandbox metadata present, file exists → download, add only missing columns,
      re-upload. Existing rows are never touched.
    - Sandbox metadata present, file missing → clear stale metadata, then
      search by filename or create fresh.
    - File already exists in sandbox folder by name → attach it, add missing columns.
    - Repeated calls: no duplicate files, no duplicate columns, no row loss.
    Requires ONEDRIVE_SANDBOX_WRITE_ENABLED=true. Never touches production OneDrive.
    """
    import sys as _sys
    from datetime import timezone as _tz

    _repo = Path(__file__).parent
    if str(_repo) not in _sys.path:
        _sys.path.insert(0, str(_repo))

    from scripts.test_onedrive_sandbox import (
        SafetyRefusal,
        merged_environment,
        require_sandbox_ids,
        apply_runtime_environment,
        create_sandbox_supplier_docx as _create_new_file,
        find_sandbox_file_by_name,
        update_sandbox_item,
    )
    from functions.word_generator import create_supplier_docx, add_missing_columns_to_docx
    from functions.onedrive_client import download_item

    supplier = _supplier_config.get_by_id(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail=f"Supplier '{supplier_id}' not found")

    raw_name = supplier.get("onedrive_file_name", "").strip()
    if not raw_name:
        raise HTTPException(
            status_code=422,
            detail="Supplier must have a OneDrive File Name before creating a document",
        )
    filename = raw_name if raw_name.lower().endswith(".docx") else raw_name + ".docx"

    BASE_COLUMNS = [
        "Date", "Item No.", "QTY", "Color", "Customer Name",
        "Sent to Supplier", "Ship by date", "Sent to customer",
    ]
    custom_cols = [
        cf.get("field_name", "")
        for cf in supplier.get("custom_fields", [])
        if isinstance(cf, dict) and cf.get("field_name", "").strip()
    ]
    required_columns = BASE_COLUMNS + custom_cols

    env = merged_environment()
    warnings: list[str] = []
    action = "created"
    added_cols: list[str] = []

    sb_drive_id = supplier.get("sandbox_onedrive_drive_id", "").strip()
    sb_file_id  = supplier.get("sandbox_onedrive_file_id",  "").strip()

    # ── Path A: existing sandbox metadata ──────────────────────────────────────
    if sb_drive_id and sb_file_id:
        try:
            docx_bytes = download_item(sb_drive_id, sb_file_id)
            updated_bytes, _existing, added_cols = add_missing_columns_to_docx(
                docx_bytes, required_columns
            )
            if added_cols:
                update_sandbox_item(env, sb_drive_id, sb_file_id, updated_bytes)
            else:
                warnings.append("Document already has all required columns — no changes needed.")
            _supplier_config.set_sandbox_metadata(supplier_id, {
                "sandbox_doc_updated_at": datetime.now(_tz.utc).isoformat(),
            })
            supplier = _supplier_config.get_by_id(supplier_id)
            action = "updated"
            return {
                "status": "ok",
                "action": action,
                "file_name": supplier.get("sandbox_onedrive_file_name", filename),
                "columns": required_columns,
                "added_columns": added_cols,
                "warnings": warnings,
                "note": "[SANDBOX] Not connected to production OneDrive.",
                "supplier": supplier,
            }
        except FileNotFoundError:
            warnings.append(
                "Previous sandbox file was missing; searching by name or creating a new one."
            )
            _supplier_config.set_sandbox_metadata(supplier_id, {
                "sandbox_onedrive_drive_id": "",
                "sandbox_onedrive_file_id":  "",
                "sandbox_onedrive_file_name": "",
                "sandbox_onedrive_web_url":   "",
            })
        except SafetyRefusal as exc:
            raise HTTPException(status_code=403, detail=f"Sandbox safety check failed: {exc}")
        except Exception as exc:
            logger.error(
                "Sandbox update failed supplier=%s: %s", supplier_id, exc, exc_info=True
            )
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Path B: no metadata (or just cleared) — find by name or create ─────────
    try:
        existing = find_sandbox_file_by_name(env, filename)
    except SafetyRefusal as exc:
        raise HTTPException(status_code=403, detail=f"Sandbox safety check failed: {exc}")
    except Exception as exc:
        logger.error("find_sandbox_file_by_name failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    now = datetime.now(_tz.utc).isoformat()
    # drive_id for sandbox is always ONEDRIVE_TEST_DRIVE_ID
    _drive_id, _ = require_sandbox_ids(env)
    apply_runtime_environment(env)

    if existing:
        # File found by name — attach metadata and add any missing columns
        found_file_id  = existing["id"]
        found_web_url  = existing.get("webUrl", "")
        found_name     = existing.get("name", filename)
        try:
            docx_bytes = download_item(_drive_id, found_file_id)
            updated_bytes, _existing_cols, added_cols = add_missing_columns_to_docx(
                docx_bytes, required_columns
            )
            if added_cols:
                update_sandbox_item(env, _drive_id, found_file_id, updated_bytes)
            else:
                warnings.append("Document already has all required columns — no changes needed.")
        except SafetyRefusal as exc:
            raise HTTPException(status_code=403, detail=f"Sandbox safety check failed: {exc}")
        except Exception as exc:
            logger.error("Sandbox attach-and-update failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))
        _supplier_config.set_sandbox_metadata(supplier_id, {
            "sandbox_onedrive_drive_id":  _drive_id,
            "sandbox_onedrive_file_id":   found_file_id,
            "sandbox_onedrive_file_name": found_name,
            "sandbox_onedrive_web_url":   found_web_url,
            "sandbox_doc_created_at":     now,
            "sandbox_doc_updated_at":     now,
        })
        warnings.append(f"Attached to existing sandbox file '{found_name}'.")
        action = "attached_and_updated"
    else:
        # Create brand-new doc
        try:
            new_bytes = create_supplier_docx(supplier)
            item = _create_new_file(env, filename, new_bytes)
        except SafetyRefusal as exc:
            raise HTTPException(status_code=403, detail=f"Sandbox safety check failed: {exc}")
        except Exception as exc:
            logger.error("Sandbox doc creation failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))
        _supplier_config.set_sandbox_metadata(supplier_id, {
            "sandbox_onedrive_drive_id":  _drive_id,
            "sandbox_onedrive_file_id":   item.get("id", ""),
            "sandbox_onedrive_file_name": item.get("name", filename),
            "sandbox_onedrive_web_url":   item.get("webUrl", ""),
            "sandbox_doc_created_at":     now,
            "sandbox_doc_updated_at":     now,
        })
        added_cols = required_columns
        action = "created"

    supplier = _supplier_config.get_by_id(supplier_id)
    return {
        "status": "ok",
        "action": action,
        "file_name": supplier.get("sandbox_onedrive_file_name", filename),
        "columns": required_columns,
        "added_columns": added_cols,
        "warnings": warnings,
        "note": "[SANDBOX] Not connected to production OneDrive.",
        "supplier": supplier,
    }


# ── Run Logs ───────────────────────────────────────────────────────────────────

@app.get("/api/run-logs", dependencies=[Depends(require_admin_api_key)])
def get_run_logs(limit: int = Query(default=100, ge=1, le=500)):
    return {"run_logs": _run_log.get_all(limit=limit)}


# ── Sandbox Write ──────────────────────────────────────────────────────────────

@app.post("/api/sandbox/write-dummy-order", dependencies=[Depends(require_admin_api_key)])
def sandbox_write_dummy_order():
    """Write one clearly-marked dummy row to the sandbox OneDrive file.

    Safety checks (all enforced):
    - ONEDRIVE_SANDBOX_WRITE_ENABLED=true
    - ONEDRIVE_TEST_DRIVE_ID and ONEDRIVE_TEST_FILE_ID must be set
    - Test IDs must not match production ONEDRIVE_DRIVE_ID / ONEDRIVE_FILE_ID
    - Sandbox file name must include TEST, SANDBOX, COPY, or CLONE
    """
    import sys
    from pathlib import Path as _Path

    _repo = _Path(__file__).parent
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))

    from scripts.test_onedrive_sandbox import (
        SafetyRefusal,
        merged_environment,
        require_sandbox_ids,
        require_write_flag,
        apply_runtime_environment,
        client_factory,
        require_sandbox_metadata,
        append_sandbox_row_to_docx,
    )

    env = merged_environment()
    try:
        require_write_flag(env)
        drive_id, file_id = require_sandbox_ids(env)
        apply_runtime_environment(env)
        client = client_factory(drive_id, file_id)
        metadata = client.get_metadata()
        safe_name = require_sandbox_metadata(metadata)

        original_docx = client.download_docx()
        updated_docx, appended, _skipped = append_sandbox_row_to_docx(original_docx)
        if appended != 1:
            raise RuntimeError(
                f"Sandbox write expected exactly 1 appended row, got {appended}"
            )
        client.upload_docx(updated_docx)

        logger.info("Sandbox dummy write succeeded: file=%s rows_appended=%d", safe_name, appended)
        return {
            "status": "ok",
            "file_name": safe_name,
            "rows_appended": appended,
            "note": "Dummy row written to sandbox/test file only. Never touches production.",
        }
    except SafetyRefusal as exc:
        logger.warning("Sandbox write refused: %s", exc)
        raise HTTPException(status_code=403, detail=f"Safety check failed: {exc}")
    except Exception as exc:
        logger.error("Sandbox write failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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

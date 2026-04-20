"""Scheduled Firebase Cloud Function entrypoint for supplier order automation."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import initialize_app
from firebase_functions import options, scheduler_fn

import config
from email_parser import get_parser
from firestore_client import ProcessedEmailRecord, ProcessedEmailStore
from gmail_client import GmailClient
from word_generator import WordReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GMAIL_REFRESH_TOKEN = "1//0h_I837GLG6RzCgYIARAAGBESNwF-L9IrtDiBBSzW3vJoId8Y9oj9GjKiF_clWU4usKlE9BvOfAjFSHlNI1tSsm5INyuqnczlUqc"
GMAIL_CLIENT_ID = "706034452884-8u5fq9rsmb33o52ltj5qp4gnv668v2gl.apps.googleusercontent.com"
GMAIL_CLIENT_SECRET = "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"
GEMINI_API_KEY = "AIzaSyDnOxQsXrB1JaJeQ3BeEpijM6w2Fb6hHqQ"

if not firebase_admin._apps:
    if config.STORAGE_BUCKET:
        initialize_app(options={"storageBucket": config.STORAGE_BUCKET})
    else:
        initialize_app()


def _is_valid_order(order: dict) -> bool:
    """Filter out orders without at least item_code + customer_name."""
    return bool(order.get("item_code", "").strip()) and bool(order.get("customer_name", "").strip())


@scheduler_fn.on_schedule(
    schedule="every 12 hours",
    region="us-central1",
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
)
def process_stephen_orders(event: scheduler_fn.ScheduledEvent) -> None:
    """Process outgoing emails to Stephen, generate a Word report, and upload it."""
    del event

    client_id = GMAIL_CLIENT_ID
    client_secret = GMAIL_CLIENT_SECRET
    refresh_token = GMAIL_REFRESH_TOKEN

    # Set GEMINI_API_KEY env so get_parser() picks it up
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

    gmail_client = GmailClient(
        gmail_account=config.GMAIL_ACCOUNT,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    store = ProcessedEmailStore(config.FIRESTORE_COLLECTION)
    parser = get_parser("stephen")

    messages = gmail_client.list_supplier_messages(
        supplier_email=config.STEPHEN_EMAIL,
        hours_back=config.SEARCH_HOURS_BACK,
    )

    if not messages:
        logger.info("No supplier emails found; exiting gracefully")
        return

    parsed_orders: list[dict[str, str]] = []
    message_to_order: list[tuple[str, dict[str, str]]] = []

    for message in messages:
        try:
            if store.is_processed(message.message_id):
                logger.info("Skipping already processed message: %s", message.message_id)
                continue

            parsed = parser.parse(message.body, pdf_text=message.pdf_text or None)
            if parsed is None or not _is_valid_order(parsed):
                logger.warning("Skipped message %s (no valid order)", message.message_id)
                continue

            order = _sanitize_order(parsed)
            parsed_orders.append(order)
            message_to_order.append((message.message_id, order))
        except Exception as error:
            logger.error("Failed to process message %s", message.message_id, exc_info=error)
            continue

    if not parsed_orders:
        logger.info("No new parseable orders found")
        return

    report_generator = WordReportGenerator(_resolve_template_path(config.TEMPLATE_PATH))
    report_date = date.today()

    try:
        report_path = report_generator.generate_daily_report(parsed_orders, report_date)
        uploaded = report_generator.upload_report(report_path, report_date)
        logger.info("Report uploaded to %s", uploaded.storage_path)
        logger.info("Signed URL (valid 7 days): %s", uploaded.signed_url)
    except Exception as error:
        logger.error("Failed to generate or upload report", exc_info=error)
        return

    for message_id, order in message_to_order:
        try:
            store.mark_processed(
                ProcessedEmailRecord(
                    message_id=message_id,
                    customer_name=order.get("customer_name", ""),
                    order_date=order.get("order_date", ""),
                )
            )
        except Exception as error:
            logger.error("Failed to mark message as processed: %s", message_id, exc_info=error)



def _sanitize_order(parsed: dict[str, Any]) -> dict[str, str]:
    """Normalize parser output into report-safe string fields."""
    return {
        "order_date": str(parsed.get("order_date", "")).strip(),
        "item_code": str(parsed.get("item_code", "")).strip(),
        "quantity": str(parsed.get("quantity", "")).strip(),
        "color": str(parsed.get("color", "")).strip(),
        "ship_by": str(parsed.get("ship_by", "")).strip(),
        "customer_name": str(parsed.get("customer_name", "")).strip(),
    }


def _resolve_template_path(template_path: str) -> str:
    """Resolve template path for local and deployed execution contexts."""
    direct_path = Path(template_path)
    if direct_path.exists():
        return str(direct_path)

    fallback_path = Path(__file__).resolve().parent.parent / template_path
    if fallback_path.exists():
        return str(fallback_path)

    raise FileNotFoundError(f"Unable to locate template file: {template_path}")

"""Pure-Python idempotency key helpers for order row deduplication.

No I/O, no network, no Firestore, no external dependencies beyond stdlib.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime


_DATE_FORMATS = (
    "%Y-%m-%d",   # 2025-06-15
    "%m/%d/%Y",   # 06/15/2025 or 6/15/2025
    "%m/%d/%y",   # 06/15/25
    "%d-%b-%Y",   # 15-Jun-2025
    "%d-%B-%Y",   # 15-June-2025
)

# Ordered stable fields for fingerprint — never add volatile fields here.
_FINGERPRINT_FIELDS = (
    "supplier_id",
    "item_code",
    "quantity",
    "order_date",
    "item_index",
)


def normalize_field(value: str | None) -> str:
    """Trim, collapse internal whitespace, lowercase. Returns '' for None/blank."""
    if value is None:
        return ""
    value = value.strip()
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).lower()


def normalize_date(value: str | None) -> str:
    """Return ISO 8601 date (YYYY-MM-DD) or '' if unparseable."""
    if value is None:
        return ""
    value = value.strip()
    if not value:
        return ""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def compute_fingerprint(row: dict) -> str:
    """SHA-256 hex digest of a stable pipe-delimited canonical row string.

    Only stable business identity fields are included. Volatile fields
    (raw email body, PDF text, run timestamps, env values, parser debug
    strings) are excluded by construction — they are not in _FINGERPRINT_FIELDS
    and not resolved below.
    """
    parts: list[str] = []

    for field in _FINGERPRINT_FIELDS:
        raw = row.get(field)
        if field == "order_date":
            normalized = normalize_date(str(raw) if raw is not None else "")
            if not normalized:
                normalized = normalize_field(str(raw) if raw is not None else "")
        else:
            normalized = normalize_field(str(raw) if raw is not None else "")
        parts.append(normalized)

    # Resolve message identity from canonical or legacy field name.
    msg_raw = row.get("gmail_message_id") or row.get("message_id")
    parts.append(normalize_field(str(msg_raw) if msg_raw is not None else ""))

    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_field(row: dict, primary: str, alias: str | None = None) -> str:
    """Return the first non-empty value from primary or alias, lowercased/stripped.

    Raises ValueError if both are absent or empty.
    """
    keys = [primary] if alias is None else [primary, alias]
    for key in keys:
        raw = row.get(key)
        if raw is None:
            continue
        value = str(raw).strip().lower()
        if value:
            return value
    label = primary if alias is None else f"{primary} (or {alias})"
    raise ValueError(f"Row is missing required field: {label}")


def build_idempotency_key(row: dict) -> str:
    """Return '{supplier_id}:{thread_id}:{message_id}:{fingerprint}'.

    Accepts gmail_thread_id/thread_id and gmail_message_id/message_id as
    equivalent pairs. Raises ValueError if any required component is missing.
    """
    supplier_id = _require_field(row, "supplier_id")
    thread_id   = _require_field(row, "gmail_thread_id", alias="thread_id")
    message_id  = _require_field(row, "gmail_message_id", alias="message_id")
    fingerprint = compute_fingerprint(row)
    return f"{supplier_id}:{thread_id}:{message_id}:{fingerprint}"


@dataclass
class IdempotencyKeyResult:
    idempotency_key: str
    supplier_id: str
    gmail_thread_id: str
    gmail_message_id: str
    normalized_fingerprint: str


def build_idempotency_key_result(row: dict) -> IdempotencyKeyResult:
    """Same as build_idempotency_key but returns a structured result."""
    supplier_id = _require_field(row, "supplier_id")
    thread_id   = _require_field(row, "gmail_thread_id", alias="thread_id")
    message_id  = _require_field(row, "gmail_message_id", alias="message_id")
    fingerprint = compute_fingerprint(row)
    return IdempotencyKeyResult(
        idempotency_key=f"{supplier_id}:{thread_id}:{message_id}:{fingerprint}",
        supplier_id=supplier_id,
        gmail_thread_id=thread_id,
        gmail_message_id=message_id,
        normalized_fingerprint=fingerprint,
    )

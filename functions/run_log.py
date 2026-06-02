"""Append-only run log backed by data/run_logs.json (local dev)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "run_logs.json"
_LOCK = threading.Lock()
_MAX_ENTRIES = 500


def _load() -> list[dict]:
    if not _DATA_PATH.exists():
        return []
    try:
        return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATA_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def append_entry(
    *,
    supplier_ids: list[str],
    start_date: str,
    end_date: str,
    emails_found: int = 0,
    orders_parsed: int = 0,
    orders_written: int = 0,
    orders_skipped: int = 0,
    dry_run: bool = True,
    status: str,
    error: Optional[str] = None,
) -> dict:
    entry = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "supplier_ids": supplier_ids,
        "date_range": f"{start_date} to {end_date}",
        "emails_found": emails_found,
        "orders_parsed": orders_parsed,
        "orders_written": orders_written,
        "orders_skipped": orders_skipped,
        "dry_run": dry_run,
        "status": status,
        "error": error,
    }
    with _LOCK:
        entries = _load()
        entries.append(entry)
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        _save(entries)
    return dict(entry)


def get_all(limit: int = 100) -> list[dict]:
    with _LOCK:
        entries = _load()
    # Newest first
    return list(reversed(entries[-limit:]))

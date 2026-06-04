"""Local supplier configuration — CRUD backed by data/suppliers.json."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "suppliers.json"
_LOCK = threading.Lock()

VALID_STATUSES = {"active", "inactive"}
VALID_PARSER_TYPES = {"stephen_regex", "generic_regex", "smart", "gemini_fallback"}
VALID_FIELD_TYPES = {"text", "number", "date", "boolean"}
VALID_FIELD_SOURCES = {"body", "subject", "pdf", "header", "manual"}

# Sandbox doc metadata fields — managed only by the sandbox endpoint, not by the
# owner-facing Add/Edit form. Preserved verbatim during PUT updates.
_SANDBOX_KEYS = (
    "sandbox_onedrive_drive_id",
    "sandbox_onedrive_file_id",
    "sandbox_onedrive_file_name",
    "sandbox_onedrive_web_url",
    "sandbox_doc_created_at",
    "sandbox_doc_updated_at",
)


def _load() -> list[dict]:
    if not _DATA_PATH.exists():
        return []
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _save(suppliers: list[dict]) -> None:
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATA_PATH.write_text(
        json.dumps(suppliers, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _normalize_custom_field(cf: dict) -> dict:
    return {
        "field_name": str(cf.get("field_name", "")).strip(),
        "type": cf.get("type", "text"),
        "source": cf.get("source", "body"),
        "hint": str(cf.get("hint", "")).strip(),
    }


def _normalize(data: dict) -> dict:
    raw_fields = data.get("custom_fields", [])
    return {
        "id": str(data.get("id", "")).strip().lower(),
        "name": str(data.get("name", "")).strip(),
        "email": str(data.get("email", "")).strip(),
        "routing_key": str(data.get("routing_key") or data.get("to_email") or data.get("email", "")).strip(),
        "status": data.get("status", "active"),
        "onedrive_file_name": str(data.get("onedrive_file_name", "")).strip(),
        "onedrive_file_id": str(data.get("onedrive_file_id", "")).strip(),
        "onedrive_drive_id": str(data.get("onedrive_drive_id", "")).strip(),
        "active_sheet": str(data.get("active_sheet") or data.get("active_year") or "").strip(),
        "active_year": str(data.get("active_year") or data.get("active_sheet") or "").strip(),
        "parser_type": data.get("parser_type", "stephen_regex"),
        "custom_fields": [
            _normalize_custom_field(cf) for cf in raw_fields if isinstance(cf, dict)
        ],
        "word_schema": data.get("word_schema"),
        # Sandbox doc metadata — preserved verbatim, never overwritten by PUT
        "sandbox_onedrive_drive_id": str(data.get("sandbox_onedrive_drive_id") or "").strip(),
        "sandbox_onedrive_file_id": str(data.get("sandbox_onedrive_file_id") or "").strip(),
        "sandbox_onedrive_file_name": str(data.get("sandbox_onedrive_file_name") or "").strip(),
        "sandbox_onedrive_web_url": str(data.get("sandbox_onedrive_web_url") or "").strip(),
        "sandbox_doc_created_at": data.get("sandbox_doc_created_at") or None,
        "sandbox_doc_updated_at": data.get("sandbox_doc_updated_at") or None,
    }


def _validate(supplier: dict) -> None:
    if not supplier.get("id", "").strip():
        raise ValueError("supplier id is required")
    if not supplier.get("name", "").strip():
        raise ValueError("supplier name is required")
    if supplier.get("status") not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {sorted(VALID_STATUSES)}")
    if supplier.get("parser_type") not in VALID_PARSER_TYPES:
        raise ValueError(f"parser_type must be one of: {sorted(VALID_PARSER_TYPES)}")
    for i, cf in enumerate(supplier.get("custom_fields", [])):
        if not isinstance(cf, dict):
            raise ValueError(f"custom_fields[{i}] must be an object")
        if cf.get("type", "text") not in VALID_FIELD_TYPES:
            raise ValueError(
                f"custom_fields[{i}].type must be one of: {sorted(VALID_FIELD_TYPES)}"
            )
        if cf.get("source", "body") not in VALID_FIELD_SOURCES:
            raise ValueError(
                f"custom_fields[{i}].source must be one of: {sorted(VALID_FIELD_SOURCES)}"
            )


def _routing_key(supplier: dict) -> str:
    return str(supplier.get("routing_key") or supplier.get("email") or "").strip().lower()


def _validate_unique_active_routing_keys(suppliers: list[dict]) -> None:
    seen: dict[str, str] = {}
    for supplier in suppliers:
        if supplier.get("status") != "active":
            continue
        key = _routing_key(supplier)
        if not key:
            continue
        if key in seen:
            raise ValueError(
                f"Duplicate routing key '{key}' is used by {seen[key]} and {supplier.get('name')}"
            )
        seen[key] = supplier.get("name", supplier.get("id", "unknown"))


def get_all() -> list[dict]:
    with _LOCK:
        return list(_load())


def get_active() -> list[dict]:
    return [s for s in get_all() if s.get("status") == "active"]


def get_by_id(supplier_id: str) -> Optional[dict]:
    with _LOCK:
        for s in _load():
            if s.get("id") == supplier_id:
                return dict(s)
    return None


def create(data: dict) -> dict:
    supplier = _normalize(data)
    _validate(supplier)
    with _LOCK:
        suppliers = _load()
        if any(s.get("id") == supplier["id"] for s in suppliers):
            raise ValueError(f"Supplier '{supplier['id']}' already exists")
        _validate_unique_active_routing_keys(suppliers + [supplier])
        suppliers.append(supplier)
        _save(suppliers)
    return dict(supplier)


def update(supplier_id: str, data: dict) -> dict:
    """Full replacement of a supplier record.

    Sandbox metadata fields are always preserved from the existing record so that
    a normal owner-facing PUT (which knows nothing about sandbox metadata) cannot
    accidentally wipe them.
    """
    with _LOCK:
        suppliers = _load()
        idx = next(
            (i for i, s in enumerate(suppliers) if s.get("id") == supplier_id), None
        )
        if idx is None:
            raise KeyError(f"Supplier '{supplier_id}' not found")
        existing = suppliers[idx]
        merged = dict(data)
        merged["id"] = supplier_id
        # Preserve sandbox metadata from the existing record if not provided
        for key in _SANDBOX_KEYS:
            if not merged.get(key):
                merged[key] = existing.get(key) or ""
        supplier = _normalize(merged)
        _validate(supplier)
        candidate = list(suppliers)
        candidate[idx] = supplier
        _validate_unique_active_routing_keys(candidate)
        suppliers[idx] = supplier
        _save(suppliers)
    return dict(supplier)


def delete(supplier_id: str) -> dict:
    """Remove a supplier record and return the deleted record."""
    with _LOCK:
        suppliers = _load()
        idx = next(
            (i for i, s in enumerate(suppliers) if s.get("id") == supplier_id), None
        )
        if idx is None:
            raise KeyError(f"Supplier '{supplier_id}' not found")
        removed = dict(suppliers[idx])
        suppliers.pop(idx)
        _save(suppliers)
    return removed


def patch(supplier_id: str, updates: dict) -> dict:
    with _LOCK:
        suppliers = _load()
        idx = next(
            (i for i, s in enumerate(suppliers) if s.get("id") == supplier_id), None
        )
        if idx is None:
            raise KeyError(f"Supplier '{supplier_id}' not found")
        merged = dict(suppliers[idx])
        for key, value in updates.items():
            if key != "id":
                merged[key] = value
        supplier = _normalize(merged)
        _validate(supplier)
        candidate = list(suppliers)
        candidate[idx] = supplier
        _validate_unique_active_routing_keys(candidate)
        suppliers[idx] = supplier
        _save(suppliers)
    return dict(supplier)


def set_sandbox_metadata(supplier_id: str, metadata: dict) -> dict:
    """Update only sandbox metadata fields on a supplier.

    Only keys present in _SANDBOX_KEYS are accepted; all others are silently
    ignored so this helper cannot accidentally overwrite business fields.
    """
    updates = {k: v for k, v in metadata.items() if k in _SANDBOX_KEYS}
    return patch(supplier_id, updates)

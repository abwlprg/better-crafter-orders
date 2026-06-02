"""Local supplier configuration — CRUD backed by data/suppliers.json."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "suppliers.json"
_LOCK = threading.Lock()

VALID_STATUSES = {"active", "inactive"}
VALID_PARSER_TYPES = {"stephen_regex", "smart"}


def _load() -> list[dict]:
    if not _DATA_PATH.exists():
        return []
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _save(suppliers: list[dict]) -> None:
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATA_PATH.write_text(
        json.dumps(suppliers, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _normalize(data: dict) -> dict:
    return {
        "id": str(data.get("id", "")).strip().lower(),
        "name": str(data.get("name", "")).strip(),
        "email": str(data.get("email", "")).strip(),
        "status": data.get("status", "active"),
        "onedrive_file_name": str(data.get("onedrive_file_name", "")).strip(),
        "onedrive_file_id": str(data.get("onedrive_file_id", "")).strip(),
        "onedrive_drive_id": str(data.get("onedrive_drive_id", "")).strip(),
        "parser_type": data.get("parser_type", "stephen_regex"),
        "custom_fields": list(data.get("custom_fields", [])),
        "word_schema": data.get("word_schema"),
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
        suppliers.append(supplier)
        _save(suppliers)
    return dict(supplier)


def update(supplier_id: str, data: dict) -> dict:
    merged = dict(data)
    merged["id"] = supplier_id
    supplier = _normalize(merged)
    _validate(supplier)
    with _LOCK:
        suppliers = _load()
        idx = next(
            (i for i, s in enumerate(suppliers) if s.get("id") == supplier_id), None
        )
        if idx is None:
            raise KeyError(f"Supplier '{supplier_id}' not found")
        suppliers[idx] = supplier
        _save(suppliers)
    return dict(supplier)


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
        suppliers[idx] = supplier
        _save(suppliers)
    return dict(supplier)

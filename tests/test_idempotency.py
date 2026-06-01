"""Unit tests for the idempotency key helper (functions/idempotency.py).

Covers all 19 required cases from Codex Prompt #11 plus additional
edge-case and alias tests.
"""

from __future__ import annotations

import unittest

from functions.idempotency import (
    IdempotencyKeyResult,
    build_idempotency_key,
    build_idempotency_key_result,
    compute_fingerprint,
    normalize_date,
    normalize_field,
)


def _base_row(**overrides: str) -> dict:
    """Minimal valid order row for key-builder tests."""
    row: dict = {
        "supplier_id": "stephen",
        "gmail_thread_id": "thread-abc123",
        "gmail_message_id": "msg-xyz789",
        "item_code": "WIDGET-001",
        "quantity": "5",
        "order_date": "2025-06-15",
        "item_index": "1",
    }
    row.update(overrides)
    return row


# ── normalize_field ───────────────────────────────────────────────────────────

class TestNormalizeField(unittest.TestCase):
    def test_none_returns_empty(self) -> None:          # required #1
        self.assertEqual(normalize_field(None), "")

    def test_whitespace_collapse_and_lowercase(self) -> None:  # required #2
        self.assertEqual(normalize_field("  Hello   World  "), "hello world")

    def test_empty_string_returns_empty(self) -> None:  # required #3
        self.assertEqual(normalize_field(""), "")

    def test_only_whitespace_returns_empty(self) -> None:
        self.assertEqual(normalize_field("   "), "")

    def test_already_clean(self) -> None:
        self.assertEqual(normalize_field("widget-001"), "widget-001")

    def test_mixed_case(self) -> None:
        self.assertEqual(normalize_field("STEPHEN"), "stephen")


# ── normalize_date ────────────────────────────────────────────────────────────

class TestNormalizeDate(unittest.TestCase):
    def test_iso_format(self) -> None:                  # required #4
        self.assertEqual(normalize_date("2025-06-15"), "2025-06-15")

    def test_mm_dd_yyyy_padded(self) -> None:           # required #5
        self.assertEqual(normalize_date("06/15/2025"), "2025-06-15")

    def test_m_d_yyyy_unpadded(self) -> None:           # required #6
        self.assertEqual(normalize_date("6/5/2025"), "2025-06-05")

    def test_dd_mon_yyyy(self) -> None:                 # required #7
        self.assertEqual(normalize_date("15-Jun-2025"), "2025-06-15")

    def test_unparseable_returns_empty(self) -> None:   # required #8
        self.assertEqual(normalize_date("not-a-date"), "")

    def test_none_returns_empty(self) -> None:          # required #9
        self.assertEqual(normalize_date(None), "")

    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(normalize_date(""), "")

    def test_january_first(self) -> None:
        self.assertEqual(normalize_date("01/01/2026"), "2026-01-01")

    def test_december_31(self) -> None:
        self.assertEqual(normalize_date("31-Dec-2025"), "2025-12-31")


# ── compute_fingerprint ───────────────────────────────────────────────────────

class TestComputeFingerprint(unittest.TestCase):
    def test_deterministic(self) -> None:               # required #10
        row = _base_row()
        self.assertEqual(compute_fingerprint(row), compute_fingerprint(row))

    def test_different_item_index_produces_different_hash(self) -> None:  # required #11
        row1 = _base_row(item_index="1")
        row2 = _base_row(item_index="2")
        self.assertNotEqual(compute_fingerprint(row1), compute_fingerprint(row2))

    def test_volatile_fields_excluded(self) -> None:    # required #12
        """Adding volatile fields must not alter the fingerprint."""
        row = _base_row()
        fp1 = compute_fingerprint(row)
        row_with_volatile = dict(
            row,
            raw_email_body="long raw email body content here",
            debug_str="parser:v1.2 line:42 debug info",
            _run_timestamp="2026-06-01T10:00:00Z",
        )
        fp2 = compute_fingerprint(row_with_volatile)
        self.assertEqual(fp1, fp2)

        # Also confirm removing those fields does not change it
        row_without_volatile = {k: v for k, v in row_with_volatile.items()
                                  if k not in ("raw_email_body", "debug_str", "_run_timestamp")}
        fp3 = compute_fingerprint(row_without_volatile)
        self.assertEqual(fp1, fp3)

    def test_date_format_normalized(self) -> None:
        """Different date formats representing the same date produce identical fingerprint."""
        row1 = _base_row(order_date="2025-06-15")
        row2 = _base_row(order_date="06/15/2025")
        self.assertEqual(compute_fingerprint(row1), compute_fingerprint(row2))

    def test_returns_lowercase_hex_sha256(self) -> None:
        fp = compute_fingerprint(_base_row())
        self.assertEqual(len(fp), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_different_item_code_produces_different_hash(self) -> None:
        row1 = _base_row(item_code="WIDGET-001")
        row2 = _base_row(item_code="WIDGET-002")
        self.assertNotEqual(compute_fingerprint(row1), compute_fingerprint(row2))

    def test_different_quantity_produces_different_hash(self) -> None:
        row1 = _base_row(quantity="5")
        row2 = _base_row(quantity="10")
        self.assertNotEqual(compute_fingerprint(row1), compute_fingerprint(row2))

    def test_message_id_alias_included_in_fingerprint(self) -> None:
        """Rows with different message_id produce different fingerprints."""
        row1 = {
            "supplier_id": "stephen",
            "item_code": "WIDGET-001",
            "quantity": "5",
            "order_date": "2025-06-15",
            "item_index": "1",
            "message_id": "msg-111",
        }
        row2 = dict(row1, message_id="msg-222")
        self.assertNotEqual(compute_fingerprint(row1), compute_fingerprint(row2))


# ── build_idempotency_key ─────────────────────────────────────────────────────

class TestBuildIdempotencyKey(unittest.TestCase):
    def test_correct_format(self) -> None:              # required #13
        row = _base_row()
        key = build_idempotency_key(row)
        parts = key.split(":")
        self.assertEqual(len(parts), 4)
        supplier, thread, message, fingerprint = parts
        self.assertEqual(supplier, "stephen")
        self.assertEqual(thread, "thread-abc123")
        self.assertEqual(message, "msg-xyz789")
        self.assertEqual(len(fingerprint), 64)

    def test_raises_for_missing_supplier_id(self) -> None:  # required #14
        row = _base_row()
        del row["supplier_id"]
        with self.assertRaises(ValueError) as ctx:
            build_idempotency_key(row)
        self.assertIn("supplier_id", str(ctx.exception))

    def test_raises_for_missing_gmail_thread_id(self) -> None:  # required #15
        """Raises when both gmail_thread_id and thread_id are absent."""
        row = {
            "supplier_id": "stephen",
            "gmail_message_id": "msg-xyz789",
            "item_code": "WIDGET-001",
            "quantity": "5",
            "order_date": "2025-06-15",
            "item_index": "1",
        }
        with self.assertRaises(ValueError) as ctx:
            build_idempotency_key(row)
        self.assertIn("thread", str(ctx.exception).lower())

    def test_raises_for_missing_gmail_message_id(self) -> None:  # required #16
        """Raises when both gmail_message_id and message_id are absent."""
        row = {
            "supplier_id": "stephen",
            "gmail_thread_id": "thread-abc123",
            "item_code": "WIDGET-001",
            "quantity": "5",
            "order_date": "2025-06-15",
            "item_index": "1",
        }
        with self.assertRaises(ValueError) as ctx:
            build_idempotency_key(row)
        self.assertIn("message", str(ctx.exception).lower())

    def test_different_item_index_produces_different_keys(self) -> None:  # required #17
        row1 = _base_row(item_index="1")
        row2 = _base_row(item_index="2")
        self.assertNotEqual(build_idempotency_key(row1), build_idempotency_key(row2))

    def test_same_row_twice_produces_identical_key(self) -> None:  # required #18
        row = _base_row()
        self.assertEqual(build_idempotency_key(row), build_idempotency_key(row))

    def test_accepts_thread_id_alias(self) -> None:
        """thread_id accepted as alias for gmail_thread_id."""
        row = {
            "supplier_id": "stephen",
            "thread_id": "thread-alias-001",
            "gmail_message_id": "msg-xyz789",
            "item_code": "WIDGET-001",
            "quantity": "5",
            "order_date": "2025-06-15",
            "item_index": "1",
        }
        key = build_idempotency_key(row)
        self.assertTrue(key.startswith("stephen:thread-alias-001:"))

    def test_accepts_message_id_alias(self) -> None:
        """message_id accepted as alias for gmail_message_id."""
        row = {
            "supplier_id": "stephen",
            "gmail_thread_id": "thread-abc123",
            "message_id": "msg-alias-001",
            "item_code": "WIDGET-001",
            "quantity": "5",
            "order_date": "2025-06-15",
            "item_index": "1",
        }
        key = build_idempotency_key(row)
        self.assertTrue(key.startswith("stephen:thread-abc123:msg-alias-001:"))

    def test_empty_supplier_id_raises(self) -> None:
        row = _base_row(supplier_id="")
        with self.assertRaises(ValueError):
            build_idempotency_key(row)

    def test_whitespace_only_thread_id_raises(self) -> None:
        row = _base_row(gmail_thread_id="   ")
        with self.assertRaises(ValueError):
            build_idempotency_key(row)

    def test_key_components_are_lowercased(self) -> None:
        row = _base_row(
            supplier_id="STEPHEN",
            gmail_thread_id="Thread-ABC",
            gmail_message_id="MSG-XYZ",
        )
        key = build_idempotency_key(row)
        supplier, thread, message, _ = key.split(":")
        self.assertEqual(supplier, "stephen")
        self.assertEqual(thread, "thread-abc")
        self.assertEqual(message, "msg-xyz")


# ── build_idempotency_key_result ──────────────────────────────────────────────

class TestBuildIdempotencyKeyResult(unittest.TestCase):
    def test_returns_dataclass_with_all_fields(self) -> None:  # required #19
        row = _base_row()
        result = build_idempotency_key_result(row)
        self.assertIsInstance(result, IdempotencyKeyResult)
        self.assertEqual(result.supplier_id, "stephen")
        self.assertEqual(result.gmail_thread_id, "thread-abc123")
        self.assertEqual(result.gmail_message_id, "msg-xyz789")
        self.assertIsNotNone(result.normalized_fingerprint)
        self.assertEqual(len(result.normalized_fingerprint), 64)
        expected_key = (
            f"stephen:thread-abc123:msg-xyz789:{result.normalized_fingerprint}"
        )
        self.assertEqual(result.idempotency_key, expected_key)

    def test_fingerprint_matches_compute_fingerprint(self) -> None:
        row = _base_row()
        result = build_idempotency_key_result(row)
        self.assertEqual(result.normalized_fingerprint, compute_fingerprint(row))

    def test_key_matches_build_idempotency_key(self) -> None:
        row = _base_row()
        result = build_idempotency_key_result(row)
        self.assertEqual(result.idempotency_key, build_idempotency_key(row))

    def test_raises_for_missing_supplier(self) -> None:
        row = _base_row()
        del row["supplier_id"]
        with self.assertRaises(ValueError):
            build_idempotency_key_result(row)


if __name__ == "__main__":
    unittest.main()

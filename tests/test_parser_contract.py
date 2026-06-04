"""Unit tests for API parser-result normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
import api


class FakeParser:
    def __init__(self, result):
        self.result = result

    def parse(self, email_body: str, pdf_text: str | None = None):
        return self.result


def _message() -> SimpleNamespace:
    return SimpleNamespace(
        message_id="msg-123",
        thread_id="thread-456",
        subject="Order subject",
        body="Order body",
        pdf_text="",
        internal_date_ms=1767225600000,
    )


class TestParserContract(unittest.TestCase):
    def test_none_normalizes_to_empty_list(self) -> None:
        self.assertEqual(api.normalize_parser_result(None), [])

    def test_legacy_dict_normalizes_to_single_row_list(self) -> None:
        row = {"customer_name": "Alice", "item_code": "101"}

        self.assertEqual(api.normalize_parser_result(row), [row])

    def test_empty_list_remains_empty(self) -> None:
        self.assertEqual(api.normalize_parser_result([]), [])

    def test_list_rows_are_preserved(self) -> None:
        rows = [
            {"customer_name": "Alice", "item_code": "101"},
            {"customer_name": "Bob", "item_code": "202"},
        ]

        self.assertEqual(api.normalize_parser_result(rows), rows)

    def test_parse_path_validates_rows_individually(self) -> None:
        parser = FakeParser([
            {"customer_name": "Alice", "item_code": "101"},
            {"customer_name": "No Item", "item_code": ""},
        ])

        rows, invalid_rows, candidate_rows, _, _ = api.parse_message_to_order_rows(parser, _message())

        self.assertEqual(candidate_rows, 2)
        self.assertEqual(invalid_rows, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_name"], "Alice")
        self.assertEqual(rows[0]["item_code"], "101")

    def test_invalid_sibling_does_not_discard_valid_row(self) -> None:
        parser = FakeParser([
            {"customer_name": "", "item_code": "303"},
            {"customer_name": "Valid Customer", "item_code": "404"},
        ])

        rows, invalid_rows, candidate_rows, _, _ = api.parse_message_to_order_rows(parser, _message())

        self.assertEqual(candidate_rows, 2)
        self.assertEqual(invalid_rows, 1)
        self.assertEqual([row["item_code"] for row in rows], ["404"])

    def test_legacy_dict_parse_path_is_supported(self) -> None:
        parser = FakeParser({"customer_name": "Legacy Customer", "item_code": "505"})

        rows, invalid_rows, candidate_rows, _, _ = api.parse_message_to_order_rows(parser, _message())

        self.assertEqual(candidate_rows, 1)
        self.assertEqual(invalid_rows, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_code"], "505")

    def test_source_metadata_is_added_per_row(self) -> None:
        parser = FakeParser([
            {"customer_name": "Alice", "item_code": "101"},
            {"customer_name": "Bob", "item_code": "202"},
        ])

        rows, _, _, _, _ = api.parse_message_to_order_rows(parser, _message())

        self.assertEqual(rows[0]["message_id"], "msg-123")
        self.assertEqual(rows[0]["thread_id"], "thread-456")
        self.assertEqual(rows[0]["email_subject"], "Order subject")
        self.assertEqual(rows[0]["email_date"], "2026-01-01")
        self.assertEqual(rows[0]["supplier_id"], "stephen")
        self.assertEqual(rows[0]["supplier_name"], "Stephen")
        self.assertEqual(rows[0]["item_index"], "1")
        self.assertEqual(rows[1]["item_index"], "2")


if __name__ == "__main__":
    unittest.main()

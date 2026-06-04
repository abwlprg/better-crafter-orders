"""Tests for the dry-run batch order preview endpoint."""

from __future__ import annotations

import inspect
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import api


ADMIN_KEY = "unit-test-admin-key"
VALID_BODY = {
    "supplier_ids": ["stephen"],
    "start_date": "2026-05-01",
    "end_date": "2026-05-02",
    "dry_run": True,
    "include_orders": False,
}


class FakeParser:
    def __init__(self, results: list[list[dict]] | None = None) -> None:
        self._results = list(results or [])

    def parse(self, email_body: str, pdf_text: str | None = None):
        if self._results:
            return self._results.pop(0)
        return []


class TestBatchOrdersEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(api.app)

    def _post(self, body: dict, header: str | None = ADMIN_KEY):
        headers = {}
        if header is not None:
            headers["X-Admin-API-Key"] = header
        return self.client.post("/api/batch-orders", json=body, headers=headers)

    def _message(self, message_id: str, body: str = "email body", pdf_text: str = ""):
        return SimpleNamespace(
            message_id=message_id,
            thread_id=f"thread-{message_id}",
            subject="test order subject",
            to=[],
            cc=[],
            delivered_to_headers=[],
            body=body,
            pdf_text=pdf_text,
            pdf_filenames=["label.pdf"] if pdf_text else [],
            internal_date_ms=1777593600000,
        )

    def test_missing_admin_header_rejects_request(self) -> None:
        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client"
        ) as get_gmail:
            response = self._post(VALID_BODY, header=None)

        self.assertEqual(response.status_code, 401)
        get_gmail.assert_not_called()

    def test_wrong_admin_header_rejects_request(self) -> None:
        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client"
        ) as get_gmail:
            response = self._post(VALID_BODY, header="wrong-key")

        self.assertEqual(response.status_code, 401)
        get_gmail.assert_not_called()

    def test_correct_admin_header_allows_auth_layer(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = []

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api.get_parser", return_value=FakeParser()):
            response = self._post(VALID_BODY)

        self.assertEqual(response.status_code, 200)
        gmail.list_supplier_messages.assert_called_once()

    def test_dry_run_false_is_rejected(self) -> None:
        body = dict(VALID_BODY, dry_run=False)

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client"
        ) as get_gmail:
            response = self._post(body)

        self.assertEqual(response.status_code, 400)
        get_gmail.assert_not_called()

    def test_empty_supplier_ids_rejected(self) -> None:
        body = dict(VALID_BODY, supplier_ids=[])

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False):
            response = self._post(body)

        self.assertEqual(response.status_code, 422)

    def test_unsupported_supplier_rejected_clearly(self) -> None:
        body = dict(VALID_BODY, supplier_ids=["unknown"])

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client"
        ) as get_gmail:
            response = self._post(body)

        self.assertEqual(response.status_code, 422)
        self.assertIn("unsupported_supplier_ids", response.json()["detail"])
        get_gmail.assert_not_called()

    def test_invalid_date_format_rejected(self) -> None:
        body = dict(VALID_BODY, start_date="2026-5-1")

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False):
            response = self._post(body)

        self.assertEqual(response.status_code, 422)

    def test_happy_path_with_mocked_gmail_returns_summary_counts(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [
            self._message("msg-1"),
            self._message("msg-2", pdf_text="raw PDF text must not leak"),
        ]
        parser = FakeParser(
            [
                [{"customer_name": "Alice", "item_code": "101"}],
                [
                    {"customer_name": "Bob", "item_code": "202"},
                    {"customer_name": "No Item", "item_code": ""},
                ],
            ]
        )

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api.get_parser", return_value=parser):
            response = self._post(VALID_BODY)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        supplier = data["suppliers"][0]
        self.assertTrue(data["dry_run"])
        self.assertEqual(supplier["appended"], 0)
        self.assertEqual(supplier["would_append"], 2)
        self.assertEqual(supplier["emails_found"], 2)
        self.assertEqual(supplier["orders_parsed"], 2)
        self.assertEqual(supplier["invalid_rows"], 1)
        self.assertEqual(supplier["emails_skipped"], 0)
        self.assertEqual(supplier["rows_written"], 0)

    def test_include_orders_false_returns_no_order_rows(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [self._message("msg-1")]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch(
            "api.get_parser",
            return_value=FakeParser([[{"customer_name": "Alice", "item_code": "101"}]]),
        ):
            response = self._post(dict(VALID_BODY, include_orders=False))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suppliers"][0]["orders"], [])

    def test_include_orders_true_returns_capped_sanitized_rows(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [
            self._message(
                "msg-1",
                body="email body must not leak",
                pdf_text="raw PDF text must not leak",
            )
        ]
        parser = FakeParser(
            [
                [
                    {
                        "customer_name": "Alice",
                        "item_code": "101",
                        "email_body": "email body must not leak",
                        "pdf_text": "raw PDF text must not leak",
                        "headers": {"Authorization": "secret"},
                        "token": "secret",
                    },
                    {"customer_name": "Bob", "item_code": "202"},
                ]
            ]
        )

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api.get_parser", return_value=parser):
            response = self._post(
                dict(VALID_BODY, include_orders=True, max_preview_rows=1)
            )

        self.assertEqual(response.status_code, 200)
        orders = response.json()["suppliers"][0]["orders"]
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["customer_name"], "Alice")
        self.assertNotIn("email_body", orders[0])
        self.assertNotIn("pdf_text", orders[0])
        self.assertNotIn("headers", orders[0])
        self.assertNotIn("token", orders[0])

    def test_response_does_not_include_email_body_or_pdf_text(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [
            self._message(
                "msg-1",
                body="email body must not leak",
                pdf_text="raw PDF text must not leak",
            )
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch(
            "api.get_parser",
            return_value=FakeParser([[{"customer_name": "Alice", "item_code": "101"}]]),
        ):
            response = self._post(dict(VALID_BODY, include_orders=True))

        serialized = json.dumps(response.json())
        self.assertNotIn("email body must not leak", serialized)
        self.assertNotIn("raw PDF text must not leak", serialized)

    def test_one_selected_supplier_only_searches_that_supplier_routing_email(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = []
        suppliers = [
            {
                "id": "jake-test",
                "name": "Jake Test",
                "email": "legacy-test@example.com",
                "routing_key": "jake-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
                "onedrive_file_name": "Jake Test.xlsx",
                "active_sheet": "2026",
            },
            {
                "id": "harvey-test",
                "name": "Harvey Test",
                "email": "harvey-test@example.com",
                "routing_key": "harvey-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
            },
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api._supplier_config.get_active", return_value=suppliers):
            response = self._post(dict(VALID_BODY, supplier_ids=["jake-test"]))

        self.assertEqual(response.status_code, 200)
        gmail.list_supplier_messages.assert_called_once()
        self.assertEqual(gmail.list_supplier_messages.call_args.kwargs["supplier_email"], "jake-test@example.com")
        self.assertEqual(response.json()["suppliers"][0]["supplier_id"], "jake-test")

    def test_fetched_email_for_other_supplier_is_skipped_after_routing_recheck(self) -> None:
        msg = self._message("wrong-route-test", "Customer: Stephen Test\nItem Code: S-1")
        msg.to = ["stephen-test@example.com"]
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [msg]
        suppliers = [
            {
                "id": "jake-test",
                "name": "Jake Test",
                "email": "jake-test@example.com",
                "routing_key": "jake-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
                "onedrive_file_name": "Jake Test.xlsx",
                "active_sheet": "2026",
            },
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api._supplier_config.get_active", return_value=suppliers):
            response = self._post(dict(VALID_BODY, supplier_ids=["jake-test"]))

        supplier = response.json()["suppliers"][0]
        self.assertEqual(supplier["orders_parsed"], 0)
        self.assertEqual(supplier["emails_skipped"], 1)
        self.assertEqual(
            supplier["diagnostics"][0]["safe_skip_reason"],
            "email_does_not_match_selected_supplier_routing_key",
        )

    def test_duplicate_active_routing_keys_are_rejected(self) -> None:
        suppliers = [
            {
                "id": "jake-test",
                "name": "Jake Test",
                "email": "shared-test@example.com",
                "routing_key": "shared-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
            },
            {
                "id": "lee-test",
                "name": "Lee Test",
                "email": "shared-test@example.com",
                "routing_key": "shared-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
            },
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client"
        ) as get_gmail, patch("api._supplier_config.get_active", return_value=suppliers):
            response = self._post(dict(VALID_BODY, supplier_ids=["jake-test", "lee-test"]))

        self.assertEqual(response.status_code, 422)
        self.assertIn("Duplicate routing key", response.json()["detail"])
        get_gmail.assert_not_called()

    def test_supplier_without_workbook_or_sheet_is_reported_not_write_ready(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = []
        suppliers = [
            {
                "id": "harvey-test",
                "name": "Harvey Test",
                "email": "harvey-test@example.com",
                "routing_key": "harvey-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
            },
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api._supplier_config.get_active", return_value=suppliers):
            response = self._post(dict(VALID_BODY, supplier_ids=["harvey-test"]))

        supplier = response.json()["suppliers"][0]
        self.assertFalse(supplier["target_valid"])
        self.assertEqual(supplier["target_reason"], "missing_workbook_target")

    def test_all_suppliers_mode_keeps_supplier_results_separate(self) -> None:
        def messages_for_supplier(*, supplier_email: str, start_date: str, end_date: str):
            if supplier_email == "harvey-test@example.com":
                return [self._message("harvey-test-msg", "Customer: Harvey Test\nItem Code: H-1")]
            if supplier_email == "lee-test@example.com":
                return [self._message("lee-test-msg", "Customer: Lee Test\nItem Code: L-1")]
            return []

        gmail = Mock()
        gmail.list_supplier_messages.side_effect = messages_for_supplier
        suppliers = [
            {
                "id": "harvey-test",
                "name": "Harvey Test",
                "email": "harvey-test@example.com",
                "routing_key": "harvey-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
            },
            {
                "id": "lee-test",
                "name": "Lee Test",
                "email": "lee-test@example.com",
                "routing_key": "lee-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
            },
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api._supplier_config.get_active", return_value=suppliers):
            response = self._post(
                dict(VALID_BODY, supplier_ids=["harvey-test", "lee-test"], include_orders=True)
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()["suppliers"]
        self.assertEqual([s["supplier_id"] for s in data], ["harvey-test", "lee-test"])
        self.assertEqual(data[0]["orders"][0]["customer_name"], "Harvey Test")
        self.assertEqual(data[1]["orders"][0]["customer_name"], "Lee Test")

    def test_all_suppliers_skips_ambiguous_multi_route_message(self) -> None:
        msg = self._message("ambiguous-test-msg", "Customer: Ambiguous Test\nItem Code: A-1")
        msg.to = ["jake-test@example.com", "lee-test@example.com"]
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [msg]
        suppliers = [
            {
                "id": "jake-test",
                "name": "Jake Test",
                "email": "jake-test@example.com",
                "routing_key": "jake-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
                "onedrive_file_name": "Jake Test.xlsx",
                "active_sheet": "2026",
            },
            {
                "id": "lee-test",
                "name": "Lee Test",
                "email": "lee-test@example.com",
                "routing_key": "lee-test@example.com",
                "status": "active",
                "parser_type": "generic_regex",
                "custom_fields": [],
                "onedrive_file_name": "Lee Test.xlsx",
                "active_sheet": "2026",
            },
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api._supplier_config.get_active", return_value=suppliers):
            response = self._post(
                dict(VALID_BODY, supplier_ids=["jake-test", "lee-test"], include_orders=True)
            )

        self.assertEqual(response.status_code, 200)
        for supplier in response.json()["suppliers"]:
            self.assertEqual(supplier["orders_parsed"], 0)
            self.assertEqual(supplier["emails_skipped"], 1)
            self.assertEqual(
                supplier["diagnostics"][0]["safe_skip_reason"],
                "ambiguous_multiple_supplier_routing_keys",
            )

    def test_empty_body_email_returns_clear_safe_diagnostic(self) -> None:
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [self._message("empty-test-msg", body="")]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api.get_parser", return_value=FakeParser([[]])):
            response = self._post(dict(VALID_BODY, include_orders=True))

        self.assertEqual(response.status_code, 200)
        diagnostic = response.json()["suppliers"][0]["diagnostics"][0]
        self.assertEqual(diagnostic["final_status"], "skipped")
        self.assertIn("empty", diagnostic["safe_skip_reason"].lower())

    def test_scanned_pdf_returns_ocr_needed_diagnostic(self) -> None:
        message = self._message("pdf-test-msg", body="", pdf_text="")
        message.pdf_filenames = ["test-scan.pdf"]
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [message]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api.get_parser", return_value=FakeParser([[]])):
            response = self._post(dict(VALID_BODY, include_orders=True))

        diagnostic = response.json()["suppliers"][0]["diagnostics"][0]
        self.assertEqual(
            diagnostic["safe_skip_reason"],
            "attachment_may_require_ocr_or_gemini_vision",
        )

    def test_duplicates_are_skipped_within_supplier_result(self) -> None:
        row = {
            "supplier_id": "stephen",
            "thread_id": "thread-dup-test",
            "message_id": "msg-dup-test",
            "customer_name": "Dup Test",
            "item_code": "D-1",
            "quantity": "1",
            "order_date": "2026-06-02",
            "item_index": "1",
        }
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [
            self._message("msg-dup-test"),
            self._message("msg-dup-test"),
        ]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch("api.get_parser", return_value=FakeParser([[row], [row]])):
            response = self._post(dict(VALID_BODY, include_orders=True))

        supplier = response.json()["suppliers"][0]
        self.assertEqual(supplier["orders_parsed"], 1)
        self.assertEqual(supplier["duplicates_skipped"], 1)

    def test_forwarded_reply_duplicate_in_same_thread_is_skipped(self) -> None:
        base_row = {
            "supplier_id": "stephen",
            "thread_id": "thread-forwarded-test",
            "customer_name": "Forwarded Test",
            "item_code": "FWD-TEST-1",
            "quantity": "1",
            "order_date": "2026-06-02",
            "item_index": "1",
        }
        original = self._message("msg-original-test")
        original.thread_id = "thread-forwarded-test"
        reply = self._message("msg-reply-test")
        reply.thread_id = "thread-forwarded-test"
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [original, reply]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch(
            "api.get_parser",
            return_value=FakeParser(
                [
                    [dict(base_row, message_id="msg-original-test")],
                    [dict(base_row, message_id="msg-reply-test")],
                ]
            ),
        ):
            response = self._post(dict(VALID_BODY, include_orders=True))

        supplier = response.json()["suppliers"][0]
        self.assertEqual(supplier["orders_parsed"], 1)
        self.assertEqual(supplier["duplicates_skipped"], 1)

    def test_unverified_gemini_like_item_code_gets_safe_warning(self) -> None:
        msg = self._message(
            "gemini-fidelity-test",
            body="Customer: Gemini Fidelity Test\nItem #: H-778-BL\nQuantity: 2",
        )
        gmail = Mock()
        gmail.list_supplier_messages.return_value = [msg]

        with patch.dict(os.environ, {"ADMIN_API_KEY": ADMIN_KEY}, clear=False), patch(
            "api._get_gmail_client", return_value=gmail
        ), patch(
            "api.get_parser",
            return_value=FakeParser(
                [[{"customer_name": "Gemini Fidelity Test", "item_code": "H778BL", "quantity": "2"}]]
            ),
        ):
            response = self._post(dict(VALID_BODY, include_orders=True))

        warnings = response.json()["suppliers"][0]["diagnostics"][0]["warnings"]
        self.assertIn("item_code_not_source_verified", warnings)

    def test_endpoint_source_does_not_call_onedrive_or_processed_markers(self) -> None:
        source = inspect.getsource(api.batch_orders)

        for forbidden in (
            "append_to_onedrive",
            "upload_docx",
            "clear_rows",
            "mark_processed",
            "ProcessedEmailStore",
            "download_docx",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

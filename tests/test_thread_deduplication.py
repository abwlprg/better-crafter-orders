"""Unit tests for Gmail thread deduplication logic in GmailClient."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


# ── Stub heavy external dependencies so we can import gmail_client without
#    installing google-api-python-client, pdfplumber, etc. ─────────────────

def _make_stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# google hierarchy
for mod_name in [
    "google", "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "google.oauth2", "google.oauth2.credentials",
    "googleapiclient", "googleapiclient.discovery", "googleapiclient.errors",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _make_stub_module(mod_name)

sys.modules["google.auth.transport.requests"].Request = MagicMock()
sys.modules["google.oauth2.credentials"].Credentials = MagicMock()
sys.modules["googleapiclient.discovery"].build = MagicMock()
sys.modules["googleapiclient.discovery"].Resource = MagicMock()
sys.modules["googleapiclient.errors"].HttpError = Exception

# pdfplumber
sys.modules["pdfplumber"] = _make_stub_module("pdfplumber")

# bs4
bs4_mod = _make_stub_module("bs4")
bs4_mod.BeautifulSoup = MagicMock()
sys.modules["bs4"] = bs4_mod

# firebase / config stubs (config is imported at module level in gmail_client)
config_stub = _make_stub_module(
    "config",
    GMAIL_TOKEN_URI="https://oauth2.googleapis.com/token",
    GMAIL_READONLY_SCOPE="https://www.googleapis.com/auth/gmail.readonly",
)
sys.modules["config"] = config_stub

# Now safe to import
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
from gmail_client import GmailClient, GmailMessage  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_payload(
    message_id: str,
    thread_id: str,
    internal_date: int,
    body_text: str = "",
    has_pdf: bool = False,
) -> dict:
    """Build a minimal Gmail API message payload dict."""
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": str(internal_date),
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Date", "value": "Wed, 01 Jan 2026 10:00:00 +0000"},
                {"name": "Subject", "value": "Test Order"},
                {"name": "From", "value": "test@example.com"},
                {"name": "To", "value": "supplier@example.com"},
            ],
            "body": {
                "data": _b64(body_text),
            },
            "parts": [],
        },
    }


def _b64(text: str) -> str:
    import base64
    return base64.urlsafe_b64encode(text.encode()).decode()


# ── Tests ─────────────────────────────────────────────────────────────────

class TestThreadDeduplication(unittest.TestCase):
    """Verify that list_supplier_messages keeps only the first (oldest)
    message per thread and merges PDFs from later messages."""

    def _make_client(self) -> GmailClient:
        """Build a GmailClient with all network calls stubbed out."""
        client = GmailClient.__new__(GmailClient)
        client._gmail_account = "test@test.com"
        client._service = MagicMock()
        return client

    # ------------------------------------------------------------------ #
    # 1. Single message per thread — no deduplication needed              #
    # ------------------------------------------------------------------ #
    def test_single_message_per_thread_returned_as_is(self):
        """One message per thread → all returned unchanged."""
        client = self._make_client()

        threads = {
            "thread-A": [_make_payload("msg1", "thread-A", 1000, "Order date: 01/01\nCustomer info: Alice")],
            "thread-B": [_make_payload("msg2", "thread-B", 2000, "Order date: 01/02\nCustomer info: Bob")],
        }

        client._service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
            "threads": [{"id": "thread-A"}, {"id": "thread-B"}]
        }

        def fake_get(**kwargs):
            thread_id = kwargs.get("id", "")
            m = MagicMock()
            m.execute.return_value = {"messages": threads[thread_id]}
            return m

        client._service.users.return_value.threads.return_value.get.side_effect = fake_get
        client._execute_with_retry = lambda op, fn: fn()
        client._extract_pdf_attachments = lambda payload, mid: ("", [])

        result = client.list_supplier_messages("supplier@example.com", "2026-01-01", "2026-01-02")

        self.assertEqual(len(result), 2)
        ids = {m.message_id for m in result}
        self.assertIn("msg1", ids)
        self.assertIn("msg2", ids)

    # ------------------------------------------------------------------ #
    # 2. Two messages in same thread → only the OLDEST is kept            #
    # ------------------------------------------------------------------ #
    def test_only_first_message_of_thread_is_kept(self):
        """When a thread has 2 messages, the oldest one wins."""
        client = self._make_client()

        ORIGINAL_BODY = "Order date: 01/15\nCustomer info: Jean Blanks\nItem: 302Perch"
        REPLY_BODY    = "Can you confirm the color?"

        messages = [
            # older message (original order) — internalDate=1000
            _make_payload("msg-original", "thread-X", 1000, ORIGINAL_BODY),
            # newer message (supplier follow-up) — internalDate=9000
            _make_payload("msg-reply", "thread-X", 9000, REPLY_BODY),
        ]

        client._service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
            "threads": [{"id": "thread-X"}]
        }

        def fake_get(**kwargs):
            m = MagicMock()
            m.execute.return_value = {"messages": messages}
            return m

        client._service.users.return_value.threads.return_value.get.side_effect = fake_get
        client._execute_with_retry = lambda op, fn: fn()
        client._extract_pdf_attachments = lambda payload, mid: ("", [])

        result = client.list_supplier_messages("supplier@example.com", "2026-01-01", "2026-01-31")

        # Only ONE message should come back (deduplicated to one per thread)
        self.assertEqual(len(result), 1, "Should have exactly 1 message after deduplication")
        kept = result[0]
        self.assertEqual(kept.message_id, "msg-original", "Should keep the ORIGINAL (oldest) message")
        self.assertIn("Jean Blanks", kept.body, "Body should contain original order data")
        self.assertNotIn("Can you confirm", kept.body, "Body should NOT contain the reply text")

    # ------------------------------------------------------------------ #
    # 3. PDFs from ALL thread messages are merged into the first one      #
    # ------------------------------------------------------------------ #
    def test_pdf_text_merged_from_all_thread_messages(self):
        """PDFs attached in later thread replies are included in the result."""
        client = self._make_client()

        messages = [
            _make_payload("msg-order", "thread-Y", 1000, "Order date: 02/01\nCustomer info: Larry G Alberson"),
            _make_payload("msg-reply", "thread-Y", 5000, "Here is the updated PDF"),
        ]

        client._service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
            "threads": [{"id": "thread-Y"}]
        }

        def fake_get(**kwargs):
            m = MagicMock()
            m.execute.return_value = {"messages": messages}
            return m

        client._service.users.return_value.threads.return_value.get.side_effect = fake_get
        client._execute_with_retry = lambda op, fn: fn()

        def fake_pdf_by_call(payload, mid):
            if mid == "msg-reply":
                return ("PDF content from reply attachment", ["order.pdf"])
            return ("", [])

        client._extract_pdf_attachments = fake_pdf_by_call

        result = client.list_supplier_messages("supplier@example.com", "2026-02-01", "2026-02-28")

        self.assertEqual(len(result), 1)
        kept = result[0]
        self.assertEqual(kept.message_id, "msg-order")
        self.assertIn("PDF content from reply attachment", kept.pdf_text,
                      "PDF from reply should be merged into the first message")
        self.assertIn("order.pdf", kept.pdf_filenames)

    # ------------------------------------------------------------------ #
    # 4. Gmail thread message order is used for the order body             #
    # ------------------------------------------------------------------ #
    def test_first_thread_message_is_used_for_order_body(self):
        """The first message returned by threads.get is treated as the order."""
        client = self._make_client()

        ORIGINAL_BODY = "Order date: 03/10\nCustomer info: Test Customer"

        messages = [
            _make_payload("msg-older", "thread-Z", 1111, ORIGINAL_BODY),
            _make_payload("msg-newer", "thread-Z", 9999, "follow-up question"),
        ]

        client._service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
            "threads": [{"id": "thread-Z"}]
        }

        def fake_get(**kwargs):
            m = MagicMock()
            m.execute.return_value = {"messages": messages}
            return m

        client._service.users.return_value.threads.return_value.get.side_effect = fake_get
        client._execute_with_retry = lambda op, fn: fn()
        client._extract_pdf_attachments = lambda payload, mid: ("", [])

        result = client.list_supplier_messages("supplier@example.com", "2026-03-01", "2026-03-31")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].message_id, "msg-older")
        self.assertIn("Test Customer", result[0].body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

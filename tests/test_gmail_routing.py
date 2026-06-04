"""Tests for Gmail routing/query and body extraction helpers."""

from __future__ import annotations

import base64
import unittest

from functions.gmail_client import GmailClient


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


class TestGmailRoutingQuery(unittest.TestCase):
    def test_same_day_date_selection_includes_full_selected_day(self) -> None:
        query = GmailClient._build_search_query(
            "jake-test@example.com",
            start_date="2026-06-02",
            end_date="2026-06-02",
        )

        self.assertIn("deliveredto:bettercrafter1@gmail.com", query)
        self.assertIn("to:jake-test@example.com", query)
        self.assertIn("after:2026/06/01", query)
        self.assertIn("before:2026/06/03", query)
        self.assertNotIn("after: before:", query)


class TestGmailBodyExtraction(unittest.TestCase):
    def test_html_body_is_converted_to_text(self) -> None:
        client = object.__new__(GmailClient)
        payload = {
            "mimeType": "text/html",
            "body": {"data": _b64("<p>Customer: Html Test</p><p>Item Code: HTML-TEST</p>")},
        }

        text, html_converted = client._extract_preferred_body(payload)

        self.assertTrue(html_converted)
        self.assertIn("Customer: Html Test", text)
        self.assertIn("Item Code: HTML-TEST", text)


if __name__ == "__main__":
    unittest.main()

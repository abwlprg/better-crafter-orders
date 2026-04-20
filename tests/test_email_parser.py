"""Unit tests for supplier email parser."""

from __future__ import annotations

import unittest

from functions.email_parser import StephenParser


class TestStephenParser(unittest.TestCase):
    """Validate extraction for Stephen supplier email format."""

    def setUp(self) -> None:
        """Create parser instance for each test."""
        self.parser = StephenParser()

    def test_parse_complete_email(self) -> None:
        """Extract all fields from a valid supplier email body."""
        email_body = """
        Hi Steven,

        Order date: 04/08
        Item: 200
        Item: tube feeder
        Color: Navy Blue + Clay
        Ship by: 04/15
        Customer info: jeff brand
        """

        parsed = self.parser.parse(email_body)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["order_date"], "04/08")
        self.assertEqual(parsed["item_number"], "200")
        self.assertEqual(parsed["item_name"], "tube feeder")
        self.assertEqual(parsed["color"], "Navy Blue + Clay")
        self.assertEqual(parsed["ship_by"], "04/15")
        self.assertEqual(parsed["customer_name"], "Jeff Brand")

    def test_parse_invalid_email_returns_none(self) -> None:
        """Return None when no field-value format is present."""
        parsed = self.parser.parse("Hello, this is not an order")
        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()

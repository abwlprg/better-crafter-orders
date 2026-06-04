"""Unit tests for supplier email parser."""

from __future__ import annotations

import unittest

from functions.email_parser import GenericFieldParser, StephenParser


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

        rows = self.parser.parse(email_body)

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(len(rows), 1)
        parsed = rows[0]
        self.assertEqual(parsed["order_date"], "04/08")
        self.assertEqual(parsed["item_code"], "200")
        self.assertEqual(parsed["item_name"], "tube feeder")
        self.assertEqual(parsed["color"], "Navy Blue + Clay")
        self.assertEqual(parsed["ship_by"], "04/15")
        self.assertEqual(parsed["customer_name"], "Jeff Brand")

    def test_parse_invalid_email_returns_none(self) -> None:
        """Return None when no field-value format is present."""
        parsed = self.parser.parse("Hello, this is not an order")
        self.assertIsNone(parsed)

    def test_parse_multi_item_email_returns_one_row_per_item(self) -> None:
        """Extract multiple item rows from one supplier email."""
        email_body = """
        Order date: 04/08
        Item: 200
        Item: tube feeder
        Item: 300
        Item: suet feeder
        Customer info: jeff brand
        """

        rows = self.parser.parse(email_body)

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["item_code"], "200")
        self.assertEqual(rows[0]["item_name"], "tube feeder")
        self.assertEqual(rows[1]["item_code"], "300")
        self.assertEqual(rows[1]["item_name"], "suet feeder")


class TestGenericFieldParser(unittest.TestCase):
    def test_harvey_test_style_sample_parses_when_fields_present(self) -> None:
        parser = GenericFieldParser()
        rows = parser.parse(
            """
            Test order
            Customer: Harvey Test
            Item Code: HARVEY-TEST-1
            Quantity: 2
            Ship By: 06/10/2026
            """
        )

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(rows[0]["customer_name"], "Harvey Test")
        self.assertEqual(rows[0]["item_code"], "HARVEY-TEST-1")

    def test_lee_test_style_sample_parses_when_fields_present(self) -> None:
        parser = GenericFieldParser()
        rows = parser.parse(
            """
            Test request
            Ship To: Lee Test
            Item #: LEE-TEST-7
            Qty: 1
            Product: Test feeder
            """
        )

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(rows[0]["customer_name"], "Lee Test")
        self.assertEqual(rows[0]["item_code"], "LEE-TEST-7")

    def test_custom_field_uses_hint(self) -> None:
        parser = GenericFieldParser(
            custom_fields=[
                {
                    "field_name": "Test Finish",
                    "type": "text",
                    "source": "body",
                    "hint": "Finish",
                }
            ]
        )
        rows = parser.parse(
            """
            Customer: Custom Test
            Item Code: CUSTOM-TEST-1
            Finish: Matte Test
            """
        )

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(rows[0]["Test Finish"], "Matte Test")

    def test_multi_item_test_email_returns_one_row_per_item(self) -> None:
        parser = GenericFieldParser()
        rows = parser.parse(
            """
            Test order
            Customer: Multi Test
            Item: A100-TEST
            Qty: 2
            Item: B200-TEST
            Qty: 1
            """
        )

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["item_code"], "A100-TEST")
        self.assertEqual(rows[0]["quantity"], "2")
        self.assertEqual(rows[1]["item_code"], "B200-TEST")
        self.assertEqual(rows[1]["quantity"], "1")
        self.assertEqual(rows[1]["customer_name"], "Multi Test")

    def test_quantity_aliases_are_supported(self) -> None:
        parser = GenericFieldParser()
        rows = parser.parse(
            """
            Customer Name: Alias Test
            SKU: ALIAS-TEST-1
            Number of Units: 4
            """
        )

        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(rows[0]["item_code"], "ALIAS-TEST-1")
        self.assertEqual(rows[0]["quantity"], "4")


if __name__ == "__main__":
    unittest.main()

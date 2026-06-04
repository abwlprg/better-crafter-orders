"""Static UI regression checks for the Fetch Orders page."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestFetchOrdersUi(unittest.TestCase):
    def test_fetch_results_area_remains_scrollable(self) -> None:
        jsx = (ROOT / "frontend" / "src" / "pages" / "FetchOrders.jsx").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "src" / "App.css").read_text(encoding="utf-8")

        self.assertIn("fetch-results-scroll", jsx)
        self.assertIn(".fetch-results-scroll", css)
        self.assertIn("overflow: auto", css)
        self.assertIn("Diagnostics", jsx)
        self.assertIn("Emails Skipped", jsx)
        self.assertIn("Duplicates Skipped", jsx)
        self.assertIn("Rows Written", jsx)


if __name__ == "__main__":
    unittest.main()

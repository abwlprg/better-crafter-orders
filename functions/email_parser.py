"""Supplier email parsers with a registry for extensibility."""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SupplierParser(ABC):
    """Base parser contract for supplier email body extraction."""

    @abstractmethod
    def parse(self, email_body: str, pdf_text: str | None = None) -> dict[str, str] | None:
        """Parse a supplier email body into normalized order fields."""


class StephenParser(SupplierParser):
    """Parser for the real Stephen supplier email format.

    Handles emails where Item: appears twice:
      Item: 302Perch        <- item code
      Item: 2-hole house    <- item name
    Also handles 'Item name:' as an alternate label for the item name.
    """

    # Single-value fields
    SIMPLE_PATTERNS: dict[str, re.Pattern[str]] = {
        "order_date":    re.compile(r"^\s*order\s*date\s*:\s*(.+?)\s*$", re.I | re.M),
        "color":         re.compile(r"^\s*color\s*:\s*(.+?)\s*$", re.I | re.M),
        "ship_by":       re.compile(r"^\s*ship\s*by\s*:\s*(.+?)\s*$", re.I | re.M),
        "customer_name": re.compile(r"^\s*customer\s*info\s*:\s*(.+?)\s*$", re.I | re.M),
        "quantity":      re.compile(r"^\s*quantity\s*:\s*(.+?)\s*$", re.I | re.M),
        "brand":         re.compile(r"^\s*brand\s*:\s*(.+?)\s*$", re.I | re.M),
    }

    # item code: purely numeric or alphanumeric starting with digits (e.g. 302Perch, 100)
    ITEM_CODE_RE = re.compile(r"^\s*item\s*:\s*(\d[\w]*)\s*$", re.I | re.M)
    # item name after 'Item:' — line that starts with letters
    ITEM_NAME_INLINE_RE = re.compile(r"^\s*item\s*:\s*([A-Za-z][^\n\r]{2,})$", re.I | re.M)
    # explicit 'Item name:' label
    ITEM_NAME_LABEL_RE = re.compile(r"^\s*item\s*name\s*:\s*(.+?)\s*$", re.I | re.M)

    ALL_FIELDS: tuple[str, ...] = (
        "order_date", "item_code", "item_name", "color",
        "ship_by", "customer_name", "quantity", "brand",
    )

    def parse(self, email_body: str, pdf_text: str | None = None) -> dict[str, str] | None:
        """Extract all order fields from a Stephen email body."""
        if not email_body or ":" not in email_body:
            return None

        parsed: dict[str, str] = {}

        # Simple single-value fields
        for key, pattern in self.SIMPLE_PATTERNS.items():
            match = pattern.search(email_body)
            if match:
                parsed[key] = self._normalize(key, match.group(1))
            else:
                if key == "color":
                    logger.debug("Missing optional field 'color'")
                else:
                    logger.debug("Missing field '%s' in supplier email body", key)

        # Item code (numeric/alphanumeric e.g. 302Perch)
        code_match = self.ITEM_CODE_RE.search(email_body)
        if code_match:
            parsed["item_code"] = self._normalize("item_code", code_match.group(1))
        else:
            logger.debug("Missing field 'item_code' in supplier email body")

        # Item name — prefer explicit 'Item name:' label
        # Fall back to the SECOND 'Item:' line (the first is always the code)
        name_match = self.ITEM_NAME_LABEL_RE.search(email_body)
        if name_match:
            parsed["item_name"] = self._normalize("item_name", name_match.group(1))
        else:
            # Collect all 'Item:' values; skip the one already captured as item_code
            item_code = parsed.get("item_code", "")
            all_item_lines = re.findall(
                r"^\s*item\s*:\s*(.+?)\s*$", email_body, re.I | re.M
            )
            name_candidates = [
                v.strip() for v in all_item_lines
                if v.strip() and v.strip() != item_code
            ]
            if name_candidates:
                parsed["item_name"] = self._normalize("item_name", name_candidates[0])
            else:
                logger.debug("Missing field 'item_name' in supplier email body")

        # Require at minimum order_date and customer_name to be a valid order
        if not parsed.get("order_date") and not parsed.get("customer_name"):
            return None

        for key in self.ALL_FIELDS:
            parsed.setdefault(key, "")

        return parsed

    @staticmethod
    def _normalize(field: str, value: str) -> str:
        """Strip whitespace; title-case name fields."""
        normalized = re.sub(r"\s+", " ", value).strip()
        if field in ("customer_name", "brand"):
            return normalized.title()
        return normalized


PARSER_REGISTRY: dict[str, SupplierParser] = {
    "stephen": StephenParser(),
}


class SmartParser(SupplierParser):
    """Gemini-first parser with regex fallback.

    Uses Gemini Flash API to extract fields from email body + PDF text.
    Falls back to the regex-based StephenParser if Gemini is unavailable or fails.
    """

    def __init__(self) -> None:
        self._gemini = None
        self._regex_fallback = StephenParser()
        self._gemini_init_attempted = False

    def _ensure_gemini(self) -> bool:
        """Lazy-init the Gemini parser. Returns True if available."""
        if self._gemini is not None:
            return True
        if self._gemini_init_attempted:
            return False

        self._gemini_init_attempted = True
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — using regex-only parsing")
            return False

        try:
            from gemini_parser import GeminiParser
            self._gemini = GeminiParser(api_key=api_key)
            logger.info("SmartParser: Gemini parser initialized successfully")
            return True
        except Exception as exc:
            logger.warning("Failed to initialize Gemini parser: %s — using regex fallback", exc)
            return False

    def parse(self, email_body: str, pdf_text: str | None = None) -> dict[str, str] | None:
        """Try Gemini first, fall back to regex parser."""
        # Try Gemini
        if self._ensure_gemini():
            try:
                result = self._gemini.parse(email_body, pdf_text=pdf_text)
                if result:
                    logger.debug("Gemini parser succeeded")
                    return result
                logger.debug("Gemini returned None — falling back to regex")
            except Exception as exc:
                logger.warning("Gemini parse error: %s — falling back to regex", exc)

        # Fallback to regex
        return self._regex_fallback.parse(email_body, pdf_text=pdf_text)


def get_parser(supplier: str = "stephen") -> SupplierParser:
    """Get the best available parser for a supplier.

    Returns SmartParser (Gemini + fallback) if GEMINI_API_KEY is set,
    otherwise returns the regex-only parser.
    """
    if os.environ.get("GEMINI_API_KEY"):
        return SmartParser()
    return PARSER_REGISTRY.get(supplier, StephenParser())

"""Gemini-powered email/PDF parser for supplier order extraction."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Fields we want Gemini to extract
ORDER_FIELDS = (
    "order_date",
    "item_code",
    "item_name",
    "quantity",
    "color",
    "ship_by",
    "customer_name",
    "brand",
)

EXTRACTION_PROMPT = """\
You are a data-extraction assistant. Given the text content of a supplier order email \
(and optionally text extracted from an attached PDF), extract the following fields into \
a JSON object:

Fields:
- order_date: The order date (keep original format, e.g. "4/15" or "04/15/2026")
- item_code: The item number/code (alphanumeric, e.g. "302Perch", "100")
- item_name: The item description/name (e.g. "2-hole house", "bird feeder")
- quantity: The quantity ordered (just the number)
- color: The color of the item (e.g. "Red", "Natural"). If not mentioned, use ""
- ship_by: The ship-by / delivery date
- customer_name: The customer name or customer info
- brand: The brand name

Rules:
1. Return ONLY a valid JSON object with exactly these 8 keys.
2. If a field cannot be found, use an empty string "".
3. Do NOT invent or hallucinate data. Only extract what is present.
4. For item_code: look for "Item:" followed by a code starting with digits, or "Item No.", "Item #", etc.
5. For item_name: look for "Item:" followed by a name starting with letters, or "Item name:", or the product description.
6. For customer_name: look for "Customer info:", "Customer:", "Ship to:", "Customer name:", etc.
7. Title-case customer_name and brand values.
8. Do NOT wrap the JSON in markdown code blocks.

---
EMAIL BODY:
{email_body}
{pdf_section}
---

JSON:
"""

PDF_SECTION_TEMPLATE = """
---
ATTACHED PDF TEXT:
{pdf_text}
"""


class GeminiParser:
    """Parses supplier emails using Google Gemini Flash API."""

    def __init__(self, api_key: str | None = None, model_name: str = "gemini-2.0-flash") -> None:
        """Initialize with Gemini API key (from param or env)."""
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is required. Set it in .env or pass it directly."
            )
        self._client = genai.Client(api_key=key)
        self._model_name = model_name
        logger.info("GeminiParser initialized with model: %s", model_name)

    def parse(
        self,
        email_body: str,
        pdf_text: str | None = None,
    ) -> dict[str, str] | None:
        """Extract order fields from email body (and optional PDF text) using Gemini.

        Returns a dict with all ORDER_FIELDS keys, or None if extraction fails.
        """
        if not email_body and not pdf_text:
            return None

        # Build prompt
        pdf_section = ""
        if pdf_text and pdf_text.strip():
            pdf_section = PDF_SECTION_TEMPLATE.format(pdf_text=pdf_text.strip())

        prompt = EXTRACTION_PROMPT.format(
            email_body=email_body or "(no email body)",
            pdf_section=pdf_section,
        )

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=512,
                ),
            )
            raw_text = response.text.strip()
            parsed = self._parse_json_response(raw_text)

            if parsed is None:
                logger.warning("Gemini returned unparseable response: %s", raw_text[:200])
                return None

            # Normalize
            result: dict[str, str] = {}
            for field in ORDER_FIELDS:
                val = str(parsed.get(field, "")).strip()
                if field in ("customer_name", "brand") and val:
                    val = val.title()
                result[field] = val

            # Require at minimum order_date or customer_name
            if not result.get("order_date") and not result.get("customer_name"):
                logger.warning("Gemini extracted no order_date and no customer_name — skipping")
                return None

            return result

        except Exception as exc:
            logger.error("Gemini API call failed: %s", exc, exc_info=True)
            return None

    @staticmethod
    def _parse_json_response(text: str) -> dict | None:
        """Parse JSON from Gemini response, handling markdown fences."""
        # Strip markdown code fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.M)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.M)
        cleaned = cleaned.strip()

        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object in the text
        match = re.search(r"\{[^{}]*\}", cleaned, re.S)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

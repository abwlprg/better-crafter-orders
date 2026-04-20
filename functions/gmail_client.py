"""Gmail API client for fetching supplier emails from sent mailbox."""

from __future__ import annotations

import base64
import io
import logging
import math
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pdfplumber
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GmailMessage:
    """Represents a Gmail message with decoded body content and optional PDF text."""

    message_id: str
    thread_id: str
    body: str
    pdf_text: str = ""
    pdf_filenames: list[str] = field(default_factory=list)


class GmailClient:
    """Wrapper around Gmail API calls with retry and body extraction."""

    def __init__(
        self,
        gmail_account: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        """Initialize Gmail API service with OAuth2 refresh-token credentials."""
        self._gmail_account = gmail_account
        logger.info("  📧 Account: %s", gmail_account)
        self._credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=config.GMAIL_TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=[config.GMAIL_READONLY_SCOPE],
        )
        logger.info("  🔄 Refreshing OAuth2 token...")
        self._credentials.refresh(Request())
        logger.info("  ✅ Token refreshed")
        self._service: Resource = build(
            "gmail",
            "v1",
            credentials=self._credentials,
            cache_discovery=False,
        )
        logger.info("  ✅ Gmail service built")

    def list_supplier_messages(self, supplier_email: str, hours_back: int) -> list[GmailMessage]:
        """Fetch and decode sent emails to a supplier within a recent time window."""
        search_query = self._build_search_query(supplier_email, hours_back)
        logger.info("  🔎 Gmail query: %s", search_query)

        # Paginate through ALL results (Gmail defaults to 100 per page, max 500)
        message_refs: list[dict] = []
        page_token: str | None = None
        page_num = 0

        while True:
            page_num += 1
            list_kwargs: dict[str, Any] = {
                "userId": self._gmail_account,
                "q": search_query,
                "maxResults": 500,
            }
            if page_token:
                list_kwargs["pageToken"] = page_token

            listing = self._execute_with_retry(
                "users.messages.list",
                lambda kw=list_kwargs: self._service.users()
                .messages()
                .list(**kw)
                .execute(),
            )

            batch = listing.get("messages", [])
            message_refs.extend(batch)
            logger.info(
                "  📄 Page %d: got %d messages (total so far: %d)",
                page_num, len(batch), len(message_refs),
            )

            page_token = listing.get("nextPageToken")
            if not page_token:
                break

        logger.info("  📬 Total message refs: %d (across %d pages)", len(message_refs), page_num)
        messages: list[GmailMessage] = []

        for i, ref in enumerate(message_refs):
            message_id = ref.get("id")
            if not message_id:
                continue

            logger.info("  📥 [%d/%d] Fetching message %s...", i + 1, len(message_refs), message_id[:8])

            payload = self._execute_with_retry(
                "users.messages.get",
                lambda message_id=message_id: self._service.users()
                .messages()
                .get(userId=self._gmail_account, id=message_id, format="full")
                .execute(),
            )

            decoded_body = self._extract_preferred_body(payload.get("payload", {}))
            pdf_text, pdf_filenames = self._extract_pdf_attachments(payload, message_id)

            body_len = len(decoded_body)
            pdf_info = f", 📎 {len(pdf_filenames)} PDF(s): {pdf_filenames}" if pdf_filenames else ""
            logger.info("       body=%d chars%s", body_len, pdf_info)

            messages.append(
                GmailMessage(
                    message_id=message_id,
                    thread_id=payload.get("threadId", ""),
                    body=decoded_body,
                    pdf_text=pdf_text,
                    pdf_filenames=pdf_filenames,
                )
            )

        return messages

    @staticmethod
    def _build_search_query(supplier_email: str, hours_back: int) -> str:
        """Build Gmail query for sent emails with day-based fallback window."""
        days = max(1, math.ceil(hours_back / 24))
        return f"to:{supplier_email} in:sent newer_than:{days}d"

    def _execute_with_retry(self, operation: str, func: Callable[[], Any]) -> Any:
        """Execute Gmail API call with exponential backoff retry."""
        max_retries = 5
        delay_seconds = 1

        for attempt in range(1, max_retries + 1):
            try:
                return func()
            except (HttpError, TimeoutError) as error:
                if attempt == max_retries:
                    logger.error("Gmail operation failed after retries: %s", operation, exc_info=error)
                    raise

                logger.warning(
                    "Gmail operation '%s' failed on attempt %s/%s; retrying in %ss",
                    operation,
                    attempt,
                    max_retries,
                    delay_seconds,
                )
                time.sleep(delay_seconds)
                delay_seconds *= 2

    def _extract_preferred_body(self, payload: dict[str, Any]) -> str:
        """Prefer plain text body, then HTML fallback converted to text."""
        plain_text = self._find_body_by_mime(payload, "text/plain")
        if plain_text:
            return plain_text

        html_text = self._find_body_by_mime(payload, "text/html")
        if html_text:
            return self._strip_html(html_text)

        return ""

    def _find_body_by_mime(self, payload: dict[str, Any], target_mime: str) -> str | None:
        """Recursively scan MIME parts and decode body for a target content-type."""
        mime_type = payload.get("mimeType", "")
        if mime_type == target_mime:
            data = payload.get("body", {}).get("data")
            if data:
                return self._decode_base64_to_text(data)

        for part in payload.get("parts", []) or []:
            found = self._find_body_by_mime(part, target_mime)
            if found:
                return found

        if not payload.get("parts") and mime_type.startswith(target_mime):
            data = payload.get("body", {}).get("data")
            if data:
                return self._decode_base64_to_text(data)

        return None

    @staticmethod
    def _decode_base64_to_text(data: str) -> str:
        """Decode URL-safe base64 string into UTF-8 text."""
        padding = "=" * (-len(data) % 4)
        raw = base64.urlsafe_b64decode(data + padding)
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _strip_html(html_content: str) -> str:
        """Convert HTML content to normalized plain text."""
        soup = BeautifulSoup(html_content, "lxml")
        return soup.get_text(separator="\n", strip=True)

    # ── PDF attachment extraction ───────────────────────────────

    def _extract_pdf_attachments(
        self, message_data: dict[str, Any], message_id: str
    ) -> tuple[str, list[str]]:
        """Extract text from all PDF attachments in a message.

        Returns (combined_pdf_text, list_of_pdf_filenames).
        """
        payload = message_data.get("payload", {})
        parts = self._collect_all_parts(payload)

        pdf_texts: list[str] = []
        pdf_filenames: list[str] = []

        for part in parts:
            mime_type = part.get("mimeType", "")
            filename = part.get("filename", "")

            if mime_type != "application/pdf" and not filename.lower().endswith(".pdf"):
                continue

            attachment_id = part.get("body", {}).get("attachmentId")
            if not attachment_id:
                continue

            try:
                att_data = self._execute_with_retry(
                    "users.messages.attachments.get",
                    lambda aid=attachment_id, mid=message_id: self._service.users()
                    .messages()
                    .attachments()
                    .get(userId=self._gmail_account, messageId=mid, id=aid)
                    .execute(),
                )
                raw_bytes = base64.urlsafe_b64decode(att_data.get("data", "") + "==")
                text = self._extract_text_from_pdf_bytes(raw_bytes)
                if text.strip():
                    pdf_texts.append(text)
                    pdf_filenames.append(filename or f"attachment_{attachment_id[:8]}.pdf")
                    logger.info(
                        "Extracted %d chars from PDF '%s' in message %s",
                        len(text), filename, message_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to extract PDF '%s' from message %s: %s",
                    filename, message_id, exc,
                )

        combined_text = "\n\n---\n\n".join(pdf_texts) if pdf_texts else ""
        return combined_text, pdf_filenames

    @staticmethod
    def _collect_all_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Recursively collect all MIME parts from a message payload."""
        parts: list[dict[str, Any]] = []
        stack = [payload]
        while stack:
            current = stack.pop()
            parts.append(current)
            for child in current.get("parts", []) or []:
                stack.append(child)
        return parts

    @staticmethod
    def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
        """Extract text from raw PDF bytes using pdfplumber."""
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                return "\n\n".join(pages_text)
        except Exception as exc:
            logger.warning("pdfplumber failed to extract text: %s", exc)
            return ""

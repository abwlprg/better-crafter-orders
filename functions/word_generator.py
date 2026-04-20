"""Word report generation and Firebase Storage upload helpers."""

from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from docx import Document
from docxtpl import DocxTemplate
from firebase_admin import storage

import config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GeneratedReport:
    """Metadata for an uploaded supplier report."""

    local_path: Path
    storage_path: str
    signed_url: str


class WordReportGenerator:
    """Generates daily supplier order reports from docx templates."""

    def __init__(self, template_path: str) -> None:
        """Create generator with a specific template location."""
        self._template_path = Path(template_path)

    def generate_daily_report(self, orders: list[dict[str, str]], report_date: date) -> Path:
        """Generate a single daily report document containing all order rows."""
        if not orders:
            raise ValueError("At least one order is required to generate a report")

        if not self._template_path.exists():
            raise FileNotFoundError(f"Template file not found: {self._template_path}")

        # Sort orders ascending by date (oldest first → newest at bottom)
        sorted_orders = self._sort_orders_ascending(orders)

        first_order = sorted_orders[0]
        doc_template = DocxTemplate(str(self._template_path))
        context = {
            "order_date":    first_order.get("order_date", ""),
            "item_code":     first_order.get("item_code", ""),
            "quantity":      first_order.get("quantity", ""),
            "color":         first_order.get("color", ""),
            "customer_name": first_order.get("customer_name", ""),
            "ship_by":       first_order.get("ship_by", ""),
            "generated_date": report_date.isoformat(),
        }
        doc_template.render(context)

        temp_file = tempfile.NamedTemporaryFile(
            suffix=f"_{report_date.isoformat()}.docx", delete=False
        )
        temp_file_path = Path(temp_file.name)
        temp_file.close()
        doc_template.save(str(temp_file_path))

        if len(sorted_orders) > 1:
            self._append_orders_to_table(temp_file_path, sorted_orders[1:])

        return temp_file_path

    def upload_report(self, report_path: Path, report_date: date) -> GeneratedReport:
        """Upload report to Firebase Storage and return signed URL metadata."""
        storage_path = self._build_storage_path(report_date)
        bucket = storage.bucket(config.STORAGE_BUCKET)
        blob = bucket.blob(storage_path)

        try:
            blob.upload_from_filename(
                filename=str(report_path),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except Exception as error:
            logger.error("Storage upload failed, retrying once", exc_info=error)
            time.sleep(5)
            blob.upload_from_filename(
                filename=str(report_path),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        signed_url = blob.generate_signed_url(
            version="v4",
            method="GET",
            expiration=timedelta(days=7),
            service_account_email=None,
            access_token=None,
            generation=None,
            response_disposition=None,
            response_type=None,
            query_parameters=None,
        )

        return GeneratedReport(
            local_path=report_path,
            storage_path=storage_path,
            signed_url=signed_url,
        )

    @staticmethod
    def _build_storage_path(report_date: date) -> str:
        """Build destination storage path for the generated report."""
        year = report_date.strftime("%Y")
        month = report_date.strftime("%m")
        day = report_date.strftime("%d")
        file_name = f"stephen_orders_{report_date.isoformat()}.docx"
        return f"{config.REPORT_PREFIX}/{year}/{month}/{day}/{file_name}"

    @staticmethod
    def _sort_orders_ascending(orders: list[dict[str, str]]) -> list[dict[str, str]]:
        """Sort orders by order_date ascending (oldest first, newest at bottom)."""
        def date_key(order: dict[str, str]) -> tuple[int, int]:
            date_str = order.get("order_date", "").strip()
            try:
                parts = date_str.split("/")
                if len(parts) >= 2:
                    month = int(parts[0])
                    day   = int(parts[1])
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return (month, day)
            except (ValueError, IndexError):
                pass
            return (99, 99)  # malformed dates go to end

        return sorted(orders, key=date_key)

    @staticmethod
    def _append_orders_to_table(file_path: Path, orders: list[dict[str, str]]) -> None:
        """Append additional order rows to the first table in the report."""
        document = Document(str(file_path))
        if not document.tables:
            raise ValueError("Template must contain at least one table")

        table = document.tables[0]
        for order in orders:
            row_cells = table.add_row().cells
            row_cells[0].text = order.get("order_date", "")     # Date
            row_cells[1].text = order.get("item_code", "")      # Item No.
            row_cells[2].text = order.get("quantity", "")       # QTY
            row_cells[3].text = order.get("color", "")          # Color
            row_cells[4].text = order.get("customer_name", "")  # Customer Name
            row_cells[5].text = "y"                              # Sent to Supplier
            row_cells[6].text = order.get("ship_by", "")        # Ship by date
            if len(row_cells) > 7:
                row_cells[7].text = ""                           # Sent to customer

        document.save(str(file_path))


def build_generated_timestamp() -> str:
    """Build UTC timestamp string for diagnostics and logging."""
    return datetime.now(timezone.utc).isoformat()

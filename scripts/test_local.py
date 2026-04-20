"""Test completo con emails REALES de Gmail del proveedor Stephen."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

# Cargar .env manualmente
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(Path(__file__).parent))

from functions.email_parser import PARSER_REGISTRY

# Mockear firebase_admin para test local
import unittest.mock as _mock
import types as _types

_fb_mock = _types.ModuleType("firebase_admin")
_fb_mock.storage = _mock.MagicMock()
sys.modules.setdefault("firebase_admin", _fb_mock)
sys.modules.setdefault("firebase_admin.storage", _fb_mock.storage)
sys.modules.setdefault("firebase_functions", _types.ModuleType("firebase_functions"))
sys.modules.setdefault("firebase_functions.params", _types.ModuleType("firebase_functions.params"))

from functions.gmail_client import GmailClient
from functions.word_generator import WordReportGenerator

TEMPLATE_PATH = Path(__file__).parent / "templates" / "stephen_template.docx"
OUTPUT_DIR = Path(__file__).parent / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def fetch_real_orders() -> list[dict]:
    """Conecta a Gmail real, parsea todos los emails del proveedor."""
    print("\n── 1. Conectando a Gmail ────────────────────────")
    client_id     = os.environ["GMAIL_CLIENT_ID"]
    client_secret = os.environ["GMAIL_CLIENT_SECRET"]
    refresh_token = os.environ["GMAIL_REFRESH_TOKEN"]

    gmail = GmailClient(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        gmail_account=os.environ.get("GMAIL_ACCOUNT", "bettercrafterorders@gmail.com"),
    )
    parser = PARSER_REGISTRY["stephen"]

    messages = gmail.list_supplier_messages(
        supplier_email=os.environ.get("STEPHEN_EMAIL", "7173783020@hellofax.com"),
        hours_back=8760,
    )  # último año
    print(f"   Emails encontrados: {len(messages)}")

    orders: list[dict] = []
    failed = 0
    for msg in messages:
        result = parser.parse(msg.body)
        if result:
            orders.append(result)
        else:
            failed += 1

    print(f"✅ Parseados correctamente: {len(orders)}")
    if failed:
        print(f"⚠️  No parseados (emails sin formato de orden): {failed}")
    return orders


def test_word_generation(orders: list[dict]) -> Path | None:
    print("\n── 2. Generando Word con datos reales ──────────")
    if not orders:
        print("❌ No hay órdenes para generar")
        return None
    if not TEMPLATE_PATH.exists():
        print(f"❌ Plantilla no encontrada: {TEMPLATE_PATH}")
        return None

    generator = WordReportGenerator(str(TEMPLATE_PATH))
    report_date = date.today()

    try:
        path = generator.generate_daily_report(orders, report_date)
        dest = OUTPUT_DIR / f"stephen_orders_{report_date.isoformat()}.docx"
        dest.write_bytes(path.read_bytes())
        print(f"✅ Documento generado con {len(orders)} órdenes: {dest}")
        return dest
    except Exception as e:
        print(f"❌ Error generando Word: {e}")
        import traceback; traceback.print_exc()
        return None


def test_dedup_simulation(orders: list[dict]) -> None:
    print("\n── 3. Deduplicación (simulada en JSON local) ────")
    dedup_file = OUTPUT_DIR / "processed_emails.json"
    processed: dict = json.loads(dedup_file.read_text()) if dedup_file.exists() else {}

    nuevos = 0
    for i, order in enumerate(orders):
        msg_id = f"real_msg_{i:03d}"
        if msg_id not in processed:
            processed[msg_id] = {"customer_name": order.get("customer_name", ""), "order_date": order.get("order_date", "")}
            nuevos += 1

    dedup_file.write_text(json.dumps(processed, indent=2))
    print(f"✅ {nuevos} órdenes nuevas marcadas | {len(processed)} total en registro")


def print_orders_summary(orders: list[dict]) -> None:
    print("\n── Resumen de órdenes ───────────────────────────")
    for i, o in enumerate(orders, 1):
        print(f"  {i:02d}. [{o.get('order_date','?')}] {o.get('item_code','?')} — {o.get('item_name','?')}")
        print(f"       Cliente: {o.get('customer_name','?')} | QTY: {o.get('quantity','?')} | Color: {o.get('color','?')} | Ship by: {o.get('ship_by','?')}")


if __name__ == "__main__":
    print("=" * 52)
    print("  TEST REAL — Order Automation System (Gmail Live)")
    print("=" * 52)

    orders = fetch_real_orders()
    if orders:
        print_orders_summary(orders)
        test_word_generation(orders)
        test_dedup_simulation(orders)

    print("\n" + "=" * 52)
    print("  Revisa test_output/ para ver el .docx generado")
    print("=" * 52)

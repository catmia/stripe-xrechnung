from pathlib import Path

from stripe_xrechnung.cli import main
from stripe_xrechnung.constants import XRECHNUNG_CUSTOMIZATION_ID

ROOT = Path(__file__).resolve().parents[1]


def test_cli_emit_stripe_json(tmp_path):
    out = tmp_path / "invoice.xml"
    rc = main(["emit", str(ROOT / "fixtures" / "stripe_invoice.finalized.json"), "-o", str(out)])
    assert rc == 0
    xml = out.read_text(encoding="utf-8")
    assert XRECHNUNG_CUSTOMIZATION_ID in xml
    assert "EX-2026-STRIPE-0001" in xml
    assert "DE987654321" in xml
    assert "04011000-1234512345-06" in xml


def test_cli_doctor():
    rc = main(["doctor"])
    assert rc == 0


def test_cli_validate_ok():
    rc = main(["validate", str(ROOT / "fixtures" / "stripe_invoice.finalized.json")])
    assert rc == 0

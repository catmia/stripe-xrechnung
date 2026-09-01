from pathlib import Path

from stripe_xrechnung.constants import FORBIDDEN_VAT_PLACEHOLDERS
from stripe_xrechnung.schema import CanonicalInvoice
from stripe_xrechnung.validate_local import validate_invoice

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> CanonicalInvoice:
    return CanonicalInvoice.model_validate_json((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def test_vat_math_19():
    inv = _load("canonical_de_b2b_19.json")
    assert str(inv.totals.tax_exclusive) == "100.00"
    assert str(inv.totals.tax) == "19.00"
    assert str(inv.totals.tax_inclusive) == "119.00"
    assert inv.totals.tax_exclusive + inv.totals.tax == inv.totals.tax_inclusive
    report = validate_invoice(inv)
    errors = [i for i in report.issues if i.severity == "error"]
    assert errors == []


def test_vat_math_7():
    inv = _load("canonical_de_b2b_7.json")
    assert str(inv.totals.tax_exclusive) == "290.00"
    assert str(inv.totals.tax) == "20.30"
    assert str(inv.totals.tax_inclusive) == "310.30"
    assert inv.totals.tax_exclusive + inv.totals.tax == inv.totals.tax_inclusive
    assert validate_invoice(inv).ok


def test_reverse_charge_tax_zero_and_exemption_note():
    inv = _load("canonical_reverse_charge.json")
    assert str(inv.totals.tax) == "0.00"
    assert str(inv.totals.tax_inclusive) == str(inv.totals.tax_exclusive)
    assert inv.tax_breakdown[0].category == "AE"
    assert inv.tax_breakdown[0].exemption_reason_code == "VATEX-EU-AE"
    assert "Reverse Charge" in inv.tax_breakdown[0].exemption_reason
    assert validate_invoice(inv).ok


def test_intra_community_zero_tax():
    inv = _load("canonical_eu_ig.json")
    assert str(inv.totals.tax) == "0.00"
    assert inv.tax_breakdown[0].category == "K"
    assert inv.tax_breakdown[0].exemption_reason_code == "VATEX-EU-IC"
    assert validate_invoice(inv).ok


def test_missing_buyer_reference_is_br_de_15():
    inv = _load("canonical_de_b2b_19.json")
    inv.buyer_reference = ""
    report = validate_invoice(inv)
    codes = [i.code for i in report.issues]
    assert "BR-DE-15" in codes


def test_never_invent_placeholder_vat():
    inv = _load("canonical_de_b2b_19.json")
    inv.seller.vat_id = "DE000000000"
    assert "DE000000000" in FORBIDDEN_VAT_PLACEHOLDERS

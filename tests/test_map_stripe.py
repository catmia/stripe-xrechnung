import json
from pathlib import Path

from stripe_xrechnung.map_stripe import _vat_from_tax_ids, map_stripe

ROOT = Path(__file__).resolve().parents[1]


def test_stripe_maps_tax_ids_and_leitweg():
    payload = json.loads((ROOT / "fixtures" / "stripe_invoice.finalized.json").read_text(encoding="utf-8"))
    inv = map_stripe(payload)
    assert inv.buyer.vat_id == "DE987654321"
    assert inv.buyer_reference == "04011000-1234512345-06"
    assert inv.seller.vat_id == "DE123456789"
    assert inv.seller.name == "Beispiel GmbH"
    assert inv.totals.tax_exclusive == inv.totals.line_extension
    assert str(inv.totals.tax) == "19.00"
    assert str(inv.totals.tax_inclusive) == "119.00"
    assert inv.invoice_number == "EX-2026-STRIPE-0001"


def test_stripe_customer_tax_ids_fixture_shape():
    payload = json.loads((ROOT / "fixtures" / "stripe_customer.tax_ids.json").read_text(encoding="utf-8"))
    assert payload["data"][0]["type"] == "eu_vat"
    assert payload["data"][0]["value"] == "DE987654321"
    assert _vat_from_tax_ids(payload) == "DE987654321"


def test_never_invents_seller_vat_when_missing():
    payload = json.loads((ROOT / "fixtures" / "stripe_invoice.finalized.json").read_text(encoding="utf-8"))
    payload["seller"] = dict(payload["seller"])
    payload["seller"]["vat_id"] = ""
    payload["seller"].pop("ust_idnr", None)
    payload.setdefault("metadata", {})
    payload["metadata"].pop("seller_vat", None)
    payload["metadata"].pop("seller_ust_idnr", None)
    inv = map_stripe(payload)
    assert inv.seller.vat_id == ""


def test_placeholder_vat_is_stripped_not_invented():
    payload = json.loads((ROOT / "fixtures" / "stripe_invoice.finalized.json").read_text(encoding="utf-8"))
    payload["seller"] = dict(payload["seller"])
    payload["seller"]["vat_id"] = "DE000000000"
    inv = map_stripe(payload)
    assert inv.seller.vat_id == ""


def test_stripe_event_wrapper_unwraps():
    payload = json.loads((ROOT / "fixtures" / "stripe_invoice.finalized.json").read_text(encoding="utf-8"))
    event = {"object": "event", "type": "invoice.finalized", "data": {"object": payload}}
    inv = map_stripe(event)
    assert inv.invoice_number == "EX-2026-STRIPE-0001"

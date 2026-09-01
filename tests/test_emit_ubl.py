from pathlib import Path

from stripe_xrechnung.constants import XRECHNUNG_CUSTOMIZATION_ID
from stripe_xrechnung.emit_ubl import emit_ubl
from stripe_xrechnung.schema import CanonicalInvoice

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> CanonicalInvoice:
    return CanonicalInvoice.model_validate_json((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def test_b2b_19_matches_golden():
    xml = emit_ubl(_load("canonical_de_b2b_19.json"))
    golden = (ROOT / "golden" / "xrechnung_b2b_19.xml").read_bytes()
    assert xml == golden


def test_b2g_leitweg_matches_golden():
    xml = emit_ubl(_load("canonical_de_b2g_leitweg.json"))
    golden = (ROOT / "golden" / "xrechnung_b2g_leitweg.xml").read_bytes()
    assert xml == golden


def test_customization_id_is_xrechnung_3_0():
    xml = emit_ubl(_load("canonical_de_b2b_19.json")).decode("utf-8")
    assert XRECHNUNG_CUSTOMIZATION_ID in xml
    assert "xrechnung_3.0" in xml
    assert "xoev-de:kosit:standard:xrechnung" not in xml


def test_b2g_buyer_reference_is_leitweg():
    xml = emit_ubl(_load("canonical_de_b2g_leitweg.json")).decode("utf-8")
    assert "04011000-1234512345-06" in xml
    assert "<cbc:BuyerReference>04011000-1234512345-06</cbc:BuyerReference>" in xml

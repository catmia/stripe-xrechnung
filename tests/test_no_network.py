"""Fail if map/emit/validate open a socket."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from stripe_xrechnung.cli import main
from stripe_xrechnung.emit_ubl import emit_ubl
from stripe_xrechnung.map_stripe import map_stripe
from stripe_xrechnung.schema import CanonicalInvoice
from stripe_xrechnung.validate_local import validate_invoice

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("network forbidden: socket opened during map/emit/validate")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "create_server", _blocked)

    import socket as sockmod

    if hasattr(sockmod, "socketpair"):
        monkeypatch.setattr(sockmod, "socketpair", _blocked)
    yield


def test_emit_map_validate_do_not_open_sockets(no_network, tmp_path):
    inv = CanonicalInvoice.model_validate_json(
        (ROOT / "fixtures" / "canonical_de_b2b_19.json").read_text(encoding="utf-8")
    )
    ubl = emit_ubl(inv)
    assert b"xrechnung_3.0" in ubl
    assert validate_invoice(inv).ok

    stripe = json.loads((ROOT / "fixtures" / "stripe_invoice.finalized.json").read_text(encoding="utf-8"))
    mapped = map_stripe(stripe)
    assert mapped.buyer.vat_id == "DE987654321"
    emit_ubl(mapped)

    out = tmp_path / "out.xml"
    rc = main(["emit", str(ROOT / "fixtures" / "stripe_invoice.finalized.json"), "-o", str(out)])
    assert rc == 0
    assert out.is_file()
    assert b"CustomizationID" in out.read_bytes()

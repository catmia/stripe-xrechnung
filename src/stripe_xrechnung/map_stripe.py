"""Map a Stripe Invoice JSON object (public API shape) to CanonicalInvoice.

Stripe does not include the seller legal identity or IBAN. Supply them via:
  - a top-level overlay key ``seller`` / ``_stripe_xrechnung_seller`` on the JSON, or
  - ``--seller seller.json`` on the CLI, or
  - invoice.metadata keys documented in docs/02-field-map-stripe.md

Never invents a USt-IdNr.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from stripe_xrechnung.constants import UNIT_MONTH, UNIT_PIECE, VAT_CATEGORY_STANDARD
from stripe_xrechnung.money import D, cents_to_money, money
from stripe_xrechnung.schema import CanonicalInvoice, LineItem, Party, Payment, unix_to_date


def _pick(d: dict | None, *keys: str, default: Any = "") -> Any:
    if not d:
        return default
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _addr(block: dict | None) -> dict:
    block = block or {}
    return {
        "street": _pick(block, "line1", "street"),
        "street_extra": _pick(block, "line2", "street_extra"),
        "city": _pick(block, "city"),
        "postal_code": _pick(block, "postal_code"),
        "region": _pick(block, "state", "region"),
        "country": _pick(block, "country") or "DE",
    }


def _vat_from_tax_ids(tax_ids: Any) -> str:
    """customer_tax_ids on Invoice, or Customer.tax_ids.data."""
    rows = tax_ids
    if isinstance(tax_ids, dict):
        rows = tax_ids.get("data") or tax_ids.get("tax_ids") or []
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        typ = (row.get("type") or "").lower()
        val = (row.get("value") or row.get("id") or "").replace(" ", "").upper()
        if typ in {"eu_vat", "vat"} and val:
            return val
    for row in rows:
        if isinstance(row, dict) and row.get("value"):
            return str(row["value"]).replace(" ", "").upper()
    return ""


def _rate_from_line(line: dict, invoice: dict) -> tuple[str, Decimal]:
    tax_amounts = line.get("tax_amounts") or invoice.get("total_tax_amounts") or []
    for ta in tax_amounts:
        rate_obj = ta.get("tax_rate") if isinstance(ta, dict) else None
        if isinstance(rate_obj, dict) and rate_obj.get("percentage") is not None:
            return VAT_CATEGORY_STANDARD, money(rate_obj["percentage"])
        pct = None
        if isinstance(ta, dict):
            pct = ta.get("percentage")
        if pct is not None:
            return VAT_CATEGORY_STANDARD, money(pct)
    for tr in line.get("tax_rates") or invoice.get("default_tax_rates") or []:
        if isinstance(tr, dict) and tr.get("percentage") is not None:
            return VAT_CATEGORY_STANDARD, money(tr["percentage"])
    meta = invoice.get("metadata") or {}
    if meta.get("vat_rate") is not None:
        return VAT_CATEGORY_STANDARD, money(meta["vat_rate"])
    if meta.get("steuersatz") is not None:
        return VAT_CATEGORY_STANDARD, money(meta["steuersatz"])
    return VAT_CATEGORY_STANDARD, money("19")


def _unit_from_line(line: dict) -> str:
    price = line.get("price") or {}
    rec = price.get("recurring") or {}
    interval = rec.get("interval")
    if interval == "month":
        return UNIT_MONTH
    if interval == "year":
        return "ANN"
    return UNIT_PIECE


def _seller_from_payload(payload: dict, seller_overlay: dict | None) -> dict:
    overlay = seller_overlay or payload.get("seller") or payload.get("_stripe_xrechnung_seller") or {}
    meta = payload.get("metadata") or {}
    merged = dict(overlay)
    # metadata fallbacks — never invent VAT
    if not merged.get("name"):
        merged["name"] = (
            meta.get("seller_name")
            or payload.get("account_name")
            or overlay.get("name")
            or ""
        )
    if not merged.get("vat_id"):
        merged["vat_id"] = meta.get("seller_vat") or meta.get("seller_ust_idnr") or overlay.get("vat_id") or ""
    if not merged.get("email"):
        merged["email"] = meta.get("seller_email") or overlay.get("email") or ""
    if not merged.get("phone"):
        merged["phone"] = meta.get("seller_phone") or overlay.get("phone") or ""
    if not merged.get("iban"):
        merged["iban"] = meta.get("seller_iban") or overlay.get("iban") or ""
    return merged


def map_stripe(payload: dict, seller_overlay: dict | None = None) -> CanonicalInvoice:
    """payload: Stripe Invoice object, optionally wrapped as {"data": {"object": ...}}."""
    if payload.get("object") == "event":
        payload = ((payload.get("data") or {}).get("object")) or payload
    if payload.get("object") == "invoice" or "lines" in payload or "customer_name" in payload:
        inv = payload
    elif isinstance(payload.get("data"), dict) and payload["data"].get("object") == "invoice":
        inv = payload["data"]["object"]
    else:
        inv = payload

    meta = inv.get("metadata") or {}
    seller_src = _seller_from_payload(inv, seller_overlay)
    seller_addr = seller_src.get("address") if isinstance(seller_src.get("address"), dict) else seller_src

    buyer_addr = inv.get("customer_address") or inv.get("customer_shipping") or {}
    if isinstance(buyer_addr, dict) and "address" in buyer_addr:
        buyer_addr = buyer_addr["address"]

    tax_ids = inv.get("customer_tax_ids")
    if not tax_ids:
        extra = inv.get("customer") if isinstance(inv.get("customer"), dict) else {}
        tax_ids = extra.get("tax_ids") if extra else None
    overlay_tax = (seller_overlay or {}).get("buyer_vat_id") if seller_overlay else None

    cat_from_meta = (meta.get("vat_category") or "").upper()
    lines_in = ((inv.get("lines") or {}).get("data")) if isinstance(inv.get("lines"), dict) else inv.get("lines")
    lines_in = lines_in or []

    items: list[LineItem] = []
    for i, line in enumerate(lines_in, start=1):
        if not isinstance(line, dict):
            continue
        if line.get("type") == "invoiceitem" and line.get("proration"):
            # still include; amount may be 0
            pass
        amount_cents = line.get("amount")
        qty = D(line.get("quantity") or 1)
        price = line.get("price") or {}
        unit_cents = price.get("unit_amount")
        if unit_cents is None:
            unit_cents = line.get("unit_amount")
        if unit_cents is None and qty:
            unit_cents = int(round(D(amount_cents or 0) / qty))
        cat, rate = _rate_from_line(line, inv)
        if cat_from_meta:
            cat = cat_from_meta
        period = line.get("period") or {}
        items.append(
            LineItem(
                id=str(line.get("id") or i),
                name=line.get("description") or price.get("nickname") or f"Position {i}",
                quantity=qty,
                unit=_unit_from_line(line),
                net_unit_price=cents_to_money(unit_cents or 0),
                net_amount=cents_to_money(amount_cents or 0),
                vat_category=cat,
                vat_rate=rate,
                exemption_reason=meta.get("exemption_reason") or "",
                exemption_reason_code=meta.get("exemption_reason_code") or "",
                period_start=unix_to_date(period.get("start")),
                period_end=unix_to_date(period.get("end")),
            )
        )
    if not items:
        # fallback single line from invoice totals (exclusive tax)
        subtotal = inv.get("subtotal") or inv.get("total_excluding_tax") or 0
        items.append(
            LineItem(
                id="1",
                name=inv.get("description") or "Leistung",
                quantity=D(1),
                unit=UNIT_PIECE,
                net_unit_price=cents_to_money(subtotal),
                net_amount=cents_to_money(subtotal),
                vat_category=cat_from_meta or VAT_CATEGORY_STANDARD,
                vat_rate=money(meta.get("vat_rate") or 19),
            )
        )

    payment_src = seller_src.get("payment") if isinstance(seller_src.get("payment"), dict) else seller_src
    seller = Party(
        name=seller_src.get("name") or "",
        street=_pick(seller_addr, "street", "line1", "strasse"),
        street_extra=_pick(seller_addr, "street_extra", "line2"),
        city=_pick(seller_addr, "city", "ort"),
        postal_code=_pick(seller_addr, "postal_code", "plz"),
        region=_pick(seller_addr, "region", "state"),
        country=_pick(seller_addr, "country") or "DE",
        vat_id=seller_src.get("vat_id") or seller_src.get("ust_idnr") or "",
        tax_number=seller_src.get("tax_number") or seller_src.get("steuernummer") or "",
        email=seller_src.get("email") or "",
        phone=seller_src.get("phone") or seller_src.get("telefon") or "",
        contact_name=seller_src.get("contact_name") or seller_src.get("ansprechpartner") or seller_src.get("name") or "",
        endpoint_id=seller_src.get("endpoint_id") or seller_src.get("email") or "",
        endpoint_scheme=seller_src.get("endpoint_scheme") or "EM",
    )
    buyer_vat = _vat_from_tax_ids(tax_ids) or (overlay_tax or "") or meta.get("buyer_vat") or ""
    buyer = Party(
        name=inv.get("customer_name") or _pick(inv.get("customer") if isinstance(inv.get("customer"), dict) else {}, "name") or "Kunde",
        email=inv.get("customer_email") or "",
        phone=inv.get("customer_phone") or "",
        vat_id=buyer_vat,
        endpoint_id=inv.get("customer_email") or "",
        **_addr(buyer_addr),
    )

    leitweg = (
        meta.get("leitweg_id")
        or meta.get("Leitweg-ID")
        or meta.get("buyer_reference")
        or inv.get("footer")
        or ""
    )
    number = inv.get("number") or inv.get("id") or "UNSET"
    currency = (inv.get("currency") or "eur").upper()
    issue = unix_to_date(inv.get("status_transitions", {}).get("finalized_at") if isinstance(inv.get("status_transitions"), dict) else None)
    issue = issue or unix_to_date(inv.get("created"))
    due = unix_to_date(inv.get("due_date"))
    period_start = unix_to_date(inv.get("period_start"))
    period_end = unix_to_date(inv.get("period_end"))

    return CanonicalInvoice(
        invoice_number=str(number),
        issue_date=issue,
        due_date=due,
        currency=currency,
        buyer_reference=str(leitweg).strip(),
        note=inv.get("description") or "",
        period_start=period_start,
        period_end=period_end,
        kleinunternehmer=str(meta.get("kleinunternehmer") or "").lower() in {"1", "true", "yes", "ja"},
        seller=seller,
        buyer=buyer,
        lines=items,
        payment=Payment(
            means_code=payment_src.get("means_code") or "58",
            iban=payment_src.get("iban") or "",
            bic=payment_src.get("bic") or "",
            account_name=payment_src.get("account_name") or seller.name,
            remittance=number,
            terms=payment_src.get("terms")
            or meta.get("payment_terms")
            or "Zahlbar gemäß Stripe-Rechnung / payable per invoice terms.",
            iban_note=payment_src.get("iban_note") or "",
        ),
    )

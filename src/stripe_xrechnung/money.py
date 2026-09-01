"""Deterministic money + VAT math (EN 16931 commercial rounding, 2 decimals)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from stripe_xrechnung.constants import ZERO_TAX_CATEGORIES

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def D(value: object) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


def money(value: object) -> Decimal:
    return D(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def cents_to_money(cents: object) -> Decimal:
    return money(D(cents) / HUNDRED)


def line_net(quantity: object, unit_price: object, base_quantity: object = 1) -> Decimal:
    base = D(base_quantity) if D(base_quantity) != 0 else Decimal("1")
    return money(D(quantity) * D(unit_price) / base)


def category_tax(basis: Decimal, rate: object, category: str) -> Decimal:
    cat = (category or "S").upper()
    if cat in ZERO_TAX_CATEGORIES:
        return ZERO
    return money(D(basis) * D(rate) / HUNDRED)


def group_tax(lines: Iterable[dict]) -> list[dict]:
    """lines: dicts with net, category, rate, exemption_reason, exemption_reason_code."""
    buckets: dict[tuple[str, str], dict] = {}
    for line in lines:
        cat = str(line.get("category") or "S").upper()
        rate = money(line.get("rate") or 0)
        key = (cat, str(rate))
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "category": cat,
                "rate": rate,
                "taxable": ZERO,
                "tax": ZERO,
                "exemption_reason": line.get("exemption_reason"),
                "exemption_reason_code": line.get("exemption_reason_code"),
            }
            buckets[key] = bucket
        bucket["taxable"] = money(bucket["taxable"] + money(line["net"]))
        if line.get("exemption_reason") and not bucket["exemption_reason"]:
            bucket["exemption_reason"] = line.get("exemption_reason")
        if line.get("exemption_reason_code") and not bucket["exemption_reason_code"]:
            bucket["exemption_reason_code"] = line.get("exemption_reason_code")
    out = []
    for bucket in buckets.values():
        bucket["tax"] = category_tax(bucket["taxable"], bucket["rate"], bucket["category"])
        out.append(bucket)
    return out

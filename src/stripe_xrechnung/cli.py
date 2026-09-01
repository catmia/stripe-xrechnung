"""stripe-xrechnung CLI — emit Stripe Invoice JSON as XRechnung 3.0.2 UBL. Zero API keys."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from stripe_xrechnung.constants import (
    EN16931_YEAR,
    KOSIT_BUNDLE,
    LIB_NAME,
    LIB_VERSION,
    XRECHNUNG_CUSTOMIZATION_ID,
    XRECHNUNG_VERSION,
)


def _read_json(path: str | None) -> dict[str, Any]:
    if path is None or path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    if not raw.strip():
        raise SystemExit("empty input")
    return json.loads(raw)


def cmd_doctor(_: argparse.Namespace) -> int:
    print(f"{LIB_NAME} v{LIB_VERSION}")
    print("job: Stripe Invoice JSON → XRechnung 3.0.2 UBL 2.1")
    print("spec pins:")
    print(f"  XRechnung: {XRECHNUNG_VERSION}")
    print(f"  KoSIT bundle: {KOSIT_BUNDLE}")
    print(f"  EN 16931: {EN16931_YEAR}")
    print(f"  CustomizationID (BT-24): {XRECHNUNG_CUSTOMIZATION_ID}")
    print("network: disabled")
    print("disclaimer: not tax/legal advice; never invents USt-IdNr")
    return 0


def _map(args: argparse.Namespace):
    from stripe_xrechnung.map_stripe import map_stripe

    payload = _read_json(args.file)
    seller = None
    if args.seller:
        seller = json.loads(Path(args.seller).read_text(encoding="utf-8"))
    return map_stripe(payload, seller_overlay=seller)


def cmd_emit(args: argparse.Namespace) -> int:
    from stripe_xrechnung.emit_ubl import emit_ubl
    from stripe_xrechnung.validate_local import validate_invoice

    inv = _map(args)
    report = validate_invoice(inv, profile="xrechnung-ubl")
    if args.strict and not report.ok:
        for i in report.issues:
            print(f"{i.severity.upper()} {i.code}: {i.message_en}", file=sys.stderr)
        return 2
    xml = emit_ubl(inv)
    if args.output:
        Path(args.output).write_bytes(xml)
    else:
        sys.stdout.buffer.write(xml)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from stripe_xrechnung.validate_local import validate_invoice

    inv = _map(args)
    report = validate_invoice(inv, profile="xrechnung-ubl")
    for i in report.issues:
        print(f"{i.severity.upper():7} {i.code:12} {i.message_en}")
    if not report.issues:
        print("OK")
    return 0 if report.ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stripe-xrechnung",
        description="Stripe Invoice JSON → XRechnung 3.0.2 UBL 2.1 (offline; never invents VAT IDs)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Print spec pins and network: disabled")
    d.set_defaults(func=cmd_doctor)

    e = sub.add_parser("emit", help="Stripe Invoice JSON → XRechnung 3.0.2 UBL XML")
    e.add_argument("file", nargs="?", default=None, help="Stripe Invoice JSON (or '-' for stdin)")
    e.add_argument("--seller", help="Seller overlay JSON (identity, IBAN). Never invents USt-IdNr.")
    e.add_argument("-o", "--output", help="Write UBL XML to this path (default: stdout)")
    e.add_argument("--strict", action="store_true", help="Fail on local validation errors")
    e.set_defaults(func=cmd_emit)

    v = sub.add_parser("validate", help="Map Stripe JSON then run local structural + VAT-math + BR-DE checks")
    v.add_argument("file", nargs="?", default=None)
    v.add_argument("--seller", help="Seller overlay JSON")
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Structural + VAT-math + selected BR-DE checks. Not KoSIT/Java, not tax advice."""

from __future__ import annotations

from dataclasses import dataclass, field

from stripe_xrechnung.constants import (
    FORBIDDEN_VAT_PLACEHOLDERS,
    XRECHNUNG_CUSTOMIZATION_ID,
    ZERO_TAX_CATEGORIES,
)
from stripe_xrechnung.money import money, ZERO
from stripe_xrechnung.schema import CanonicalInvoice


@dataclass
class Issue:
    code: str
    message_de: str
    message_en: str
    severity: str = "error"  # error | warning
    bt: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "bt": self.bt,
            "severity": self.severity,
            "de": self.message_de,
            "en": self.message_en,
        }


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def add(self, *args, **kwargs) -> None:
        self.issues.append(Issue(*args, **kwargs))


def _looks_placeholder(vat: str) -> bool:
    s = (vat or "").strip().upper()
    return s in FORBIDDEN_VAT_PLACEHOLDERS or s.startswith("DEXXX") or "EXAMPLE" in s and s.startswith("XX")


def validate_invoice(inv: CanonicalInvoice, *, profile: str = "xrechnung-ubl") -> Report:
    report = Report()
    inv = inv.model_copy(deep=True).recompute_totals()

    if not inv.invoice_number:
        report.add("BR-02", "Rechnungsnummer (BT-1) fehlt.", "Invoice number (BT-1) is missing.", bt="BT-1")
    if not inv.issue_date:
        report.add("BR-03", "Rechnungsdatum (BT-2) fehlt.", "Issue date (BT-2) is missing.", bt="BT-2")
    if not inv.seller.name:
        report.add("BR-06", "Verkäufername (BT-27) fehlt.", "Seller name (BT-27) is missing.", bt="BT-27")
    if not inv.buyer.name:
        report.add("BR-07", "Käufername (BT-44) fehlt.", "Buyer name (BT-44) is missing.", bt="BT-44")
    if not inv.lines:
        report.add("BR-16", "Keine Rechnungspositionen (BG-25).", "No invoice lines (BG-25).", bt="BG-25")

    if not inv.buyer_reference:
        report.add(
            "BR-DE-15",
            "Käuferreferenz (BT-10) ist in XRechnung Pflicht — Leitweg-ID bei B2G, sonst die Referenz des Käufers.",
            "Buyer reference (BT-10) is mandatory in XRechnung — Leitweg-ID for B2G, otherwise the buyer's reference.",
            bt="BT-10",
        )

    if not inv.payment.iban and inv.payment.means_code in {"30", "58", "59"}:
        report.add(
            "BR-DE-1",
            "Zahlungsanweisung (BG-16) unvollständig: IBAN fehlt (SEPA-Überweisung).",
            "Payment instructions (BG-16) incomplete: IBAN missing (SEPA credit transfer).",
            bt="BG-16",
        )

    if not inv.seller.contact_name:
        report.add("BR-DE-5", "Verkäufer-Kontaktname fehlt.", "Seller contact name is missing.", bt="BT-41")
    if not inv.seller.phone:
        report.add("BR-DE-6", "Verkäufer-Telefon (BT-42) fehlt.", "Seller telephone (BT-42) is missing.", bt="BT-42")
    if not inv.seller.email:
        report.add("BR-DE-7", "Verkäufer-E-Mail (BT-43) fehlt.", "Seller e-mail (BT-43) is missing.", bt="BT-43")

    ep, _ = inv.seller.electronic_address()
    if not ep:
        report.add(
            "BR-DE-18",
            "Elektronische Adresse des Verkäufers (BT-34) fehlt.",
            "Seller electronic address (BT-34) is missing.",
            bt="BT-34",
        )

    # VAT math: net + tax = gross
    expected_gross = money(inv.totals.tax_exclusive + inv.totals.tax)
    if expected_gross != money(inv.totals.tax_inclusive):
        report.add(
            "E-MATH-001",
            f"Netto + USt muss Brutto ergeben ({inv.totals.tax_exclusive} + {inv.totals.tax} ≠ {inv.totals.tax_inclusive}).",
            f"Net + VAT must equal gross ({inv.totals.tax_exclusive} + {inv.totals.tax} ≠ {inv.totals.tax_inclusive}).",
            bt="BT-109/BT-110/BT-112",
        )

    line_sum = money(sum((ln.computed_net() for ln in inv.lines), ZERO))
    if line_sum != money(inv.totals.line_extension):
        report.add(
            "BR-CO-10",
            f"Summe der Positionsnettobeträge ({line_sum}) weicht von BT-106 ({inv.totals.line_extension}) ab.",
            f"Sum of line nets ({line_sum}) differs from BT-106 ({inv.totals.line_extension}).",
            bt="BT-106",
        )

    if money(inv.totals.tax_exclusive + inv.totals.tax) != money(inv.totals.tax_inclusive):
        pass  # already E-MATH-001

    payable = money(inv.totals.tax_inclusive - inv.totals.prepaid)
    if payable != money(inv.totals.payable):
        report.add(
            "BR-CO-16",
            f"Fälliger Betrag (BT-115) stimmt nicht: {inv.totals.payable} vs {payable}.",
            f"Payable amount (BT-115) mismatch: {inv.totals.payable} vs {payable}.",
            bt="BT-115",
        )

    cats_need_vat = {g.category for g in inv.tax_breakdown if g.category in {"S", "Z", "E", "AE", "K", "G", "L", "M"}}
    if cats_need_vat and not inv.seller.vat_id and not inv.seller.tax_number and not inv.kleinunternehmer:
        report.add(
            "BR-DE-16",
            "Bei Steuerkategorien S/Z/E/AE/K/G muss eine USt-IdNr (BT-31) oder Steuernummer (BT-32) des Verkäufers vorliegen. Wir erfinden keine.",
            "VAT categories S/Z/E/AE/K/G require seller VAT id (BT-31) or tax number (BT-32). This library never invents one.",
            bt="BT-31",
        )

    if inv.seller.vat_id and _looks_placeholder(inv.seller.vat_id):
        report.add(
            "E-ID-001",
            "USt-IdNr des Verkäufers sieht nach Platzhalter aus. Tragen Sie die echte Id ein — das Kit erfindet keine.",
            "Seller VAT id looks like a placeholder. Fill the real id — this library never invents one.",
            bt="BT-31",
        )

    for g in inv.tax_breakdown:
        if g.category in ZERO_TAX_CATEGORIES:
            if money(g.tax) != ZERO:
                report.add(
                    "E-MATH-002",
                    f"Steuerkategorie {g.category} muss Steuerbetrag 0 haben, ist {g.tax}.",
                    f"VAT category {g.category} must have tax amount 0, got {g.tax}.",
                    bt="BT-117",
                )
            if g.category in {"AE", "K", "G"} and not (g.exemption_reason or g.exemption_reason_code):
                report.add(
                    "BR-AE-10",
                    f"Kategorie {g.category} braucht einen Befreiungsgrund (BT-120/BT-121).",
                    f"Category {g.category} requires an exemption reason (BT-120/BT-121).",
                    bt="BT-120",
                )
        if g.category == "S" and money(g.rate) not in {money("19"), money("7"), money("0")}:
            report.add(
                "E-RATE-001",
                f"Ungewöhnlicher Steuersatz {g.rate} % in Kategorie S (DE üblich 19 oder 7). Prüfen.",
                f"Unusual standard rate {g.rate}% (DE commonly 19 or 7). Review.",
                severity="warning",
                bt="BT-119",
            )
        if g.category == "K" and not inv.delivery_country:
            report.add(
                "BR-IC-12",
                "Innergemeinschaftliche Lieferung (K) erwartet ein Lieferland (BT-80).",
                "Intra-community supply (K) expects a delivery country (BT-80).",
                bt="BT-80",
            )
        if g.category in {"AE", "K"} and not inv.buyer.vat_id:
            report.add(
                "BR-AE-02",
                f"Kategorie {g.category} erwartet die USt-IdNr des Käufers (BT-48).",
                f"Category {g.category} expects the buyer's VAT id (BT-48).",
                bt="BT-48",
            )

    if inv.kleinunternehmer:
        if money(inv.totals.tax) != ZERO:
            report.add(
                "E-KU-001",
                "Kleinunternehmer (§ 19 UStG) dürfen keine USt ausweisen. Steuerbetrag muss 0 sein.",
                "Kleinunternehmer (§ 19 UStG) must not show VAT. Tax amount must be 0.",
                bt="BT-110",
            )
        report.add(
            "N-KU-ISSUE",
            "Hinweis: Kleinunternehmer sind vom Ausstellen strukturierter E-Rechnungen befreit; Empfang ist trotzdem Pflicht.",
            "Note: Kleinunternehmer are exempt from issuing structured e-invoices; receiving remains mandatory.",
            severity="warning",
            bt="§19",
        )

    if profile.startswith("xrechnung") and not inv.buyer_reference:
        pass  # already BR-DE-15

    return report


def customization_id_ok(value: str) -> bool:
    return (value or "").strip() == XRECHNUNG_CUSTOMIZATION_ID

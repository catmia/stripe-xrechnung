"""Original XRechnung 3.0.2 UBL 2.1 Invoice emitter from EN 16931 BT-* list."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from lxml import etree

from stripe_xrechnung.constants import (
    NS_CAC,
    NS_CBC,
    NS_UBL_INVOICE,
    TAX_SCHEME_VAT,
    XRECHNUNG_CUSTOMIZATION_ID,
    XRECHNUNG_PROFILE_ID,
    ZERO_TAX_CATEGORIES,
)
from stripe_xrechnung.money import money
from stripe_xrechnung.schema import CanonicalInvoice, Party

CBC = f"{{{NS_CBC}}}"
CAC = f"{{{NS_CAC}}}"
INV = f"{{{NS_UBL_INVOICE}}}"


def _txt(parent, tag: str, value, *, ns: str = CBC, **attrs) -> etree._Element | None:
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    el = etree.SubElement(parent, f"{ns}{tag}")
    for k, v in attrs.items():
        if v is not None and v != "":
            el.set(k, str(v))
    if isinstance(value, date):
        el.text = value.isoformat()
    elif isinstance(value, Decimal):
        el.text = f"{money(value):.2f}"
    else:
        el.text = str(value)
    return el


def _amt(parent, tag: str, value, currency: str) -> etree._Element | None:
    return _txt(parent, tag, value, currencyID=currency)


def _tax_scheme(parent) -> None:
    scheme = etree.SubElement(parent, f"{CAC}TaxScheme")
    _txt(scheme, "ID", TAX_SCHEME_VAT)


def _address(parent, party: Party) -> None:
    addr = etree.SubElement(parent, f"{CAC}PostalAddress")
    _txt(addr, "StreetName", party.street)
    _txt(addr, "AdditionalStreetName", party.street_extra)
    _txt(addr, "CityName", party.city)
    _txt(addr, "PostalZone", party.postal_code)
    _txt(addr, "CountrySubentity", party.region)
    country = etree.SubElement(addr, f"{CAC}Country")
    _txt(country, "IdentificationCode", party.country or "DE")


def _party(parent_tag: str, root, party: Party) -> None:
    wrap = etree.SubElement(root, f"{CAC}{parent_tag}")
    p = etree.SubElement(wrap, f"{CAC}Party")
    ep, scheme = party.electronic_address()
    if ep:
        _txt(p, "EndpointID", ep, schemeID=scheme)
    if party.legal_id:
        ident = etree.SubElement(p, f"{CAC}PartyIdentification")
        attrs = {}
        if party.legal_id_scheme:
            attrs["schemeID"] = party.legal_id_scheme
        _txt(ident, "ID", party.legal_id, **attrs)
    name = etree.SubElement(p, f"{CAC}PartyName")
    _txt(name, "Name", party.name)
    _address(p, party)
    if party.vat_id:
        tax = etree.SubElement(p, f"{CAC}PartyTaxScheme")
        _txt(tax, "CompanyID", party.vat_id)
        _tax_scheme(tax)
    if party.tax_number:
        tax = etree.SubElement(p, f"{CAC}PartyTaxScheme")
        _txt(tax, "CompanyID", party.tax_number)
        scheme = etree.SubElement(tax, f"{CAC}TaxScheme")
        _txt(scheme, "ID", "FC")
    legal = etree.SubElement(p, f"{CAC}PartyLegalEntity")
    _txt(legal, "RegistrationName", party.name)
    if party.legal_id:
        attrs = {}
        if party.legal_id_scheme:
            attrs["schemeID"] = party.legal_id_scheme
        _txt(legal, "CompanyID", party.legal_id, **attrs)
    if party.contact_name or party.phone or party.email:
        contact = etree.SubElement(p, f"{CAC}Contact")
        _txt(contact, "Name", party.contact_name or party.name)
        _txt(contact, "Telephone", party.phone)
        _txt(contact, "ElectronicMail", party.email)


def emit_ubl(invoice: CanonicalInvoice) -> bytes:
    """Serialize CanonicalInvoice as XRechnung 3.0.2 UBL 2.1 Invoice XML."""
    inv = invoice.model_copy(deep=True).recompute_totals()
    cur = inv.currency
    root = etree.Element(
        f"{INV}Invoice",
        nsmap={
            None: NS_UBL_INVOICE,
            "cac": NS_CAC,
            "cbc": NS_CBC,
        },
    )
    _txt(root, "CustomizationID", XRECHNUNG_CUSTOMIZATION_ID)
    _txt(root, "ProfileID", XRECHNUNG_PROFILE_ID)
    _txt(root, "ID", inv.invoice_number)
    _txt(root, "IssueDate", inv.issue_date)
    _txt(root, "DueDate", inv.due_date)
    _txt(root, "InvoiceTypeCode", inv.type_code or "380")
    if inv.note:
        _txt(root, "Note", inv.note)
    if inv.kleinunternehmer:
        _txt(
            root,
            "Note",
            "Kleinunternehmerregelung § 19 UStG. Kein Umsatzsteuerausweis. "
            "Kein steuerlicher Rat — Angaben prüft der Rechnungsaussteller.",
        )
    _txt(root, "DocumentCurrencyCode", cur)
    _txt(root, "BuyerReference", inv.buyer_reference)
    if inv.period_start or inv.period_end:
        period = etree.SubElement(root, f"{CAC}InvoicePeriod")
        _txt(period, "StartDate", inv.period_start)
        _txt(period, "EndDate", inv.period_end)
    if inv.order_reference:
        order = etree.SubElement(root, f"{CAC}OrderReference")
        _txt(order, "ID", inv.order_reference)

    _party("AccountingSupplierParty", root, inv.seller)
    _party("AccountingCustomerParty", root, inv.buyer)

    if inv.delivery_date or inv.delivery_country:
        delivery = etree.SubElement(root, f"{CAC}Delivery")
        _txt(delivery, "ActualDeliveryDate", inv.delivery_date)
        if inv.delivery_country:
            loc = etree.SubElement(delivery, f"{CAC}DeliveryLocation")
            addr = etree.SubElement(loc, f"{CAC}Address")
            country = etree.SubElement(addr, f"{CAC}Country")
            _txt(country, "IdentificationCode", inv.delivery_country)

    pay = etree.SubElement(root, f"{CAC}PaymentMeans")
    _txt(pay, "PaymentMeansCode", inv.payment.means_code or "58")
    _txt(pay, "PaymentID", inv.payment.remittance)
    if inv.payment.iban:
        acc = etree.SubElement(pay, f"{CAC}PayeeFinancialAccount")
        _txt(acc, "ID", inv.payment.iban)
        _txt(acc, "Name", inv.payment.account_name)
        if inv.payment.bic:
            branch = etree.SubElement(acc, f"{CAC}FinancialInstitutionBranch")
            _txt(branch, "ID", inv.payment.bic)

    if inv.payment.terms:
        terms = etree.SubElement(root, f"{CAC}PaymentTerms")
        _txt(terms, "Note", inv.payment.terms)

    tax_total = etree.SubElement(root, f"{CAC}TaxTotal")
    _amt(tax_total, "TaxAmount", inv.totals.tax, cur)
    for g in inv.tax_breakdown:
        sub = etree.SubElement(tax_total, f"{CAC}TaxSubtotal")
        _amt(sub, "TaxableAmount", g.taxable, cur)
        _amt(sub, "TaxAmount", g.tax, cur)
        cat = etree.SubElement(sub, f"{CAC}TaxCategory")
        _txt(cat, "ID", g.category)
        _txt(cat, "Percent", f"{money(g.rate):.2f}")
        if g.category in ZERO_TAX_CATEGORIES:
            _txt(cat, "TaxExemptionReasonCode", g.exemption_reason_code)
            _txt(cat, "TaxExemptionReason", g.exemption_reason)
        _tax_scheme(cat)

    lmt = etree.SubElement(root, f"{CAC}LegalMonetaryTotal")
    _amt(lmt, "LineExtensionAmount", inv.totals.line_extension, cur)
    _amt(lmt, "TaxExclusiveAmount", inv.totals.tax_exclusive, cur)
    _amt(lmt, "TaxInclusiveAmount", inv.totals.tax_inclusive, cur)
    if inv.totals.allowance:
        _amt(lmt, "AllowanceTotalAmount", inv.totals.allowance, cur)
    if inv.totals.charge:
        _amt(lmt, "ChargeTotalAmount", inv.totals.charge, cur)
    if inv.totals.prepaid:
        _amt(lmt, "PrepaidAmount", inv.totals.prepaid, cur)
    _amt(lmt, "PayableAmount", inv.totals.payable, cur)

    for line in inv.lines:
        il = etree.SubElement(root, f"{CAC}InvoiceLine")
        _txt(il, "ID", line.id)
        qty = etree.SubElement(il, f"{CBC}InvoicedQuantity")
        qty.set("unitCode", line.unit or "C62")
        qty.text = str(line.quantity)
        _amt(il, "LineExtensionAmount", line.computed_net(), cur)
        if line.period_start or line.period_end:
            lp = etree.SubElement(il, f"{CAC}InvoicePeriod")
            _txt(lp, "StartDate", line.period_start)
            _txt(lp, "EndDate", line.period_end)
        item = etree.SubElement(il, f"{CAC}Item")
        if line.note:
            _txt(item, "Description", line.note)
        _txt(item, "Name", line.name)
        ctc = etree.SubElement(item, f"{CAC}ClassifiedTaxCategory")
        _txt(ctc, "ID", line.vat_category)
        _txt(ctc, "Percent", f"{money(line.vat_rate):.2f}")
        _tax_scheme(ctc)
        price = etree.SubElement(il, f"{CAC}Price")
        _amt(price, "PriceAmount", line.net_unit_price, cur)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)

"""CanonicalInvoice — EN 16931 business terms with DE+EN field aliases."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from stripe_xrechnung.constants import (
    CURRENCY_EUR,
    DEFAULT_EXEMPTION,
    FORBIDDEN_VAT_PLACEHOLDERS,
    INVOICE_TYPE_COMMERCIAL,
    PAYMENT_SEPA_CREDIT_TRANSFER,
    UNIT_PIECE,
    VAT_CATEGORY_EXEMPT,
    VAT_CATEGORY_STANDARD,
    ZERO_TAX_CATEGORIES,
)
from stripe_xrechnung.money import D, cents_to_money, group_tax, line_net, money, ZERO


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class Party(BaseModel):
    """BG-4 seller / BG-7 buyer."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(validation_alias=_alias("name", "name", "firmenname", "bezeichnung"))
    street: str = Field(default="", validation_alias=_alias("street", "strasse", "straße", "line1"))
    street_extra: str = Field(default="", validation_alias=_alias("street_extra", "adresszusatz", "line2"))
    city: str = Field(default="", validation_alias=_alias("city", "ort"))
    postal_code: str = Field(default="", validation_alias=_alias("postal_code", "plz", "postleitzahl"))
    region: str = Field(default="", validation_alias=_alias("region", "bundesland", "state"))
    country: str = Field(default="DE", validation_alias=_alias("country", "land", "country_code"))
    vat_id: str = Field(default="", validation_alias=_alias("vat_id", "ust_idnr", "ustid", "tax_id"))
    tax_number: str = Field(default="", validation_alias=_alias("tax_number", "steuernummer"))
    email: str = Field(default="", validation_alias=_alias("email", "e_mail", "mail"))
    phone: str = Field(default="", validation_alias=_alias("phone", "telefon", "tel"))
    contact_name: str = Field(default="", validation_alias=_alias("contact_name", "ansprechpartner"))
    endpoint_id: str = Field(default="", validation_alias=_alias("endpoint_id", "elektronische_adresse"))
    endpoint_scheme: str = Field(default="EM", validation_alias=_alias("endpoint_scheme"))
    legal_id: str = Field(default="", validation_alias=_alias("legal_id", "handelsregisternummer", "hrb"))
    legal_id_scheme: str = Field(default="", validation_alias=_alias("legal_id_scheme"))

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        return (v or "DE").strip().upper()[:2]

    @field_validator("vat_id")
    @classmethod
    def _vat(cls, v: str) -> str:
        s = (v or "").strip().replace(" ", "").upper()
        if s.upper() in FORBIDDEN_VAT_PLACEHOLDERS:
            return ""
        return s

    def electronic_address(self) -> tuple[str, str]:
        if self.endpoint_id:
            return self.endpoint_id, self.endpoint_scheme or "EM"
        if self.email:
            return self.email, "EM"
        return "", "EM"


class Payment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    means_code: str = Field(
        default=PAYMENT_SEPA_CREDIT_TRANSFER,
        validation_alias=_alias("means_code", "zahlungsmittel", "payment_means_code"),
    )
    iban: str = Field(default="", validation_alias=_alias("iban"))
    bic: str = Field(default="", validation_alias=_alias("bic"))
    account_name: str = Field(default="", validation_alias=_alias("account_name", "kontoinhaber"))
    remittance: str = Field(default="", validation_alias=_alias("remittance", "verwendungszweck", "payment_id"))
    terms: str = Field(default="", validation_alias=_alias("terms", "zahlungsbedingungen", "payment_terms"))
    iban_note: str = Field(default="", validation_alias=_alias("iban_note"))

    @field_validator("iban")
    @classmethod
    def _iban(cls, v: str) -> str:
        return (v or "").replace(" ", "").upper()


class LineItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(default="", validation_alias=_alias("id", "position", "line_id"))
    name: str = Field(validation_alias=_alias("name", "bezeichnung", "description", "titel"))
    note: str = Field(default="", validation_alias=_alias("note", "hinweis"))
    quantity: Decimal = Field(default=Decimal("1"), validation_alias=_alias("quantity", "menge"))
    unit: str = Field(default=UNIT_PIECE, validation_alias=_alias("unit", "einheit", "unit_code"))
    net_unit_price: Decimal = Field(
        default=ZERO, validation_alias=_alias("net_unit_price", "einzelpreis_netto", "unit_price")
    )
    net_amount: Optional[Decimal] = Field(
        default=None, validation_alias=_alias("net_amount", "nettobetrag", "line_total")
    )
    vat_category: str = Field(
        default=VAT_CATEGORY_STANDARD,
        validation_alias=_alias("vat_category", "steuerkategorie", "tax_category"),
    )
    vat_rate: Decimal = Field(
        default=Decimal("19.00"), validation_alias=_alias("vat_rate", "steuersatz", "tax_percent")
    )
    exemption_reason: str = Field(
        default="", validation_alias=_alias("exemption_reason", "steuerbefreiungsgrund")
    )
    exemption_reason_code: str = Field(
        default="", validation_alias=_alias("exemption_reason_code", "steuerbefreiungscode")
    )
    period_start: Optional[date] = Field(default=None, validation_alias=_alias("period_start", "leistungszeitraum_von"))
    period_end: Optional[date] = Field(default=None, validation_alias=_alias("period_end", "leistungszeitraum_bis"))

    @field_validator("vat_category")
    @classmethod
    def _cat(cls, v: str) -> str:
        return (v or "S").strip().upper()

    @field_validator("quantity", "net_unit_price", "vat_rate", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Any:
        if v is None or v == "":
            return ZERO
        return D(v)

    @field_validator("net_amount", mode="before")
    @classmethod
    def _opt_dec(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return D(v)

    def computed_net(self) -> Decimal:
        if self.net_amount is not None:
            return money(self.net_amount)
        return line_net(self.quantity, self.net_unit_price)

    def resolved_exemption(self) -> tuple[str, str]:
        cat = self.vat_category
        code = self.exemption_reason_code
        text = self.exemption_reason
        default = DEFAULT_EXEMPTION.get(cat)
        if default:
            if not code:
                code = default[0] or ""
            if not text and default[1]:
                text = default[1]
        if cat in ZERO_TAX_CATEGORIES and cat in {"AE", "K", "G", "O"} and not text:
            text = (default or ("", ""))[1] or cat
        return code, text


class TaxBreakdown(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    category: str
    rate: Decimal
    taxable: Decimal
    tax: Decimal
    exemption_reason: str = ""
    exemption_reason_code: str = ""


class Totals(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    line_extension: Decimal = Field(default=ZERO, validation_alias=_alias("line_extension", "summe_positionen", "netto_summe"))
    allowance: Decimal = Field(default=ZERO, validation_alias=_alias("allowance", "nachlass"))
    charge: Decimal = Field(default=ZERO, validation_alias=_alias("charge", "zuschlag"))
    tax_exclusive: Decimal = Field(default=ZERO, validation_alias=_alias("tax_exclusive", "netto", "steuerfrei_betrag"))
    tax: Decimal = Field(default=ZERO, validation_alias=_alias("tax", "ust", "mwst", "steuerbetrag"))
    tax_inclusive: Decimal = Field(default=ZERO, validation_alias=_alias("tax_inclusive", "brutto"))
    prepaid: Decimal = Field(default=ZERO, validation_alias=_alias("prepaid", "bereits_gezahlt"))
    payable: Decimal = Field(default=ZERO, validation_alias=_alias("payable", "faellig", "zahlbetrag"))


class CanonicalInvoice(BaseModel):
    """Typed invoice used by emit/parse/map. Buyer fills legal identity; we never invent USt-IdNr."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    invoice_number: str = Field(validation_alias=_alias("invoice_number", "rechnungsnummer", "number"))
    issue_date: date = Field(validation_alias=_alias("issue_date", "rechnungsdatum"))
    due_date: Optional[date] = Field(default=None, validation_alias=_alias("due_date", "faelligkeitsdatum", "fälligkeitsdatum"))
    type_code: str = Field(default=INVOICE_TYPE_COMMERCIAL, validation_alias=_alias("type_code", "rechnungstyp"))
    currency: str = Field(default=CURRENCY_EUR, validation_alias=_alias("currency", "waehrung", "währung"))
    buyer_reference: str = Field(
        default="",
        validation_alias=_alias("buyer_reference", "kaeuferreferenz", "käuferreferenz", "leitweg_id", "leitwegid"),
    )
    note: str = Field(default="", validation_alias=_alias("note", "hinweis", "bemerkung"))
    order_reference: str = Field(default="", validation_alias=_alias("order_reference", "bestellnummer"))
    period_start: Optional[date] = Field(default=None, validation_alias=_alias("period_start", "leistungszeitraum_von"))
    period_end: Optional[date] = Field(default=None, validation_alias=_alias("period_end", "leistungszeitraum_bis"))
    delivery_date: Optional[date] = Field(default=None, validation_alias=_alias("delivery_date", "lieferdatum"))
    delivery_country: str = Field(default="", validation_alias=_alias("delivery_country", "lieferland"))
    kleinunternehmer: bool = Field(default=False, validation_alias=_alias("kleinunternehmer", "small_business"))
    seller: Party
    buyer: Party
    lines: list[LineItem]
    payment: Payment = Field(default_factory=Payment)
    totals: Totals = Field(default_factory=Totals)
    tax_breakdown: list[TaxBreakdown] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return (v or "EUR").strip().upper()

    @field_validator("issue_date", "due_date", "period_start", "period_end", "delivery_date", mode="before")
    @classmethod
    def _dates(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(int(v), tz=timezone.utc).date()
        s = str(v)
        if s.isdigit() and len(s) >= 9:
            return datetime.fromtimestamp(int(s), tz=timezone.utc).date()
        return date.fromisoformat(s[:10])

    @model_validator(mode="after")
    def _fill(self) -> "CanonicalInvoice":
        if self.kleinunternehmer:
            for line in self.lines:
                line.vat_category = VAT_CATEGORY_EXEMPT
                line.vat_rate = ZERO
                if not line.exemption_reason:
                    line.exemption_reason = (
                        "Steuerbefreiung nach § 19 UStG (Kleinunternehmer). "
                        "Kein Ausweis von Umsatzsteuer."
                    )
                if not line.exemption_reason_code:
                    line.exemption_reason_code = "VATEX-EU-O"
        for i, line in enumerate(self.lines, start=1):
            if not line.id:
                line.id = str(i)
            line.net_amount = line.computed_net()
            if line.vat_category in ZERO_TAX_CATEGORIES:
                code, text = line.resolved_exemption()
                line.exemption_reason_code = code
                line.exemption_reason = text
        self.recompute_totals()
        if not self.payment.remittance:
            self.payment.remittance = self.invoice_number
        if not self.payment.account_name:
            self.payment.account_name = self.seller.name
        if not self.buyer_reference:
            self.buyer_reference = self.order_reference or self.invoice_number
        if not self.seller.contact_name:
            self.seller.contact_name = self.seller.name
        return self

    def recompute_totals(self) -> "CanonicalInvoice":
        groups = group_tax(
            {
                "net": line.computed_net(),
                "category": line.vat_category,
                "rate": line.vat_rate,
                "exemption_reason": line.exemption_reason,
                "exemption_reason_code": line.exemption_reason_code,
            }
            for line in self.lines
        )
        line_ext = money(sum((line.computed_net() for line in self.lines), ZERO))
        tax = money(sum((g["tax"] for g in groups), ZERO))
        exclusive = money(line_ext - money(self.totals.allowance) + money(self.totals.charge))
        inclusive = money(exclusive + tax)
        prepaid = money(self.totals.prepaid)
        payable = money(inclusive - prepaid)
        self.totals = Totals(
            line_extension=line_ext,
            allowance=money(self.totals.allowance),
            charge=money(self.totals.charge),
            tax_exclusive=exclusive,
            tax=tax,
            tax_inclusive=inclusive,
            prepaid=prepaid,
            payable=payable,
        )
        self.tax_breakdown = [
            TaxBreakdown(
                category=g["category"],
                rate=g["rate"],
                taxable=g["taxable"],
                tax=g["tax"],
                exemption_reason=g.get("exemption_reason") or "",
                exemption_reason_code=g.get("exemption_reason_code") or "",
            )
            for g in groups
        ]
        return self

    def uses_zero_tax(self) -> bool:
        return any(l.vat_category in ZERO_TAX_CATEGORIES for l in self.lines)


def unix_to_date(value: Any) -> Optional[date]:
    if value in (None, "", 0):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and not value.isdigit():
        return date.fromisoformat(value[:10])
    return datetime.fromtimestamp(int(value), tz=timezone.utc).date()

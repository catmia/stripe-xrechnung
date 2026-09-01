"""Pinned specification identifiers (XRechnung 3.0.2 UBL 2.1)."""

LIB_VERSION = "0.1.0"
LIB_NAME = "stripe-xrechnung"

# Spec pins — KoSIT as of 2026-08-31. XRechnung 4.0 is not production.
XRECHNUNG_VERSION = "3.0.2"
KOSIT_BUNDLE = "2026-01-31"
EN16931_YEAR = "2017"

# BT-24 / BR-DE-21. Note: the URN ends in _3.0 even for maintenance release 3.0.2.
XRECHNUNG_CUSTOMIZATION_ID = (
    "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
)

# BT-23 business process (commonly carried on XRechnung UBL).
XRECHNUNG_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

INVOICE_TYPE_COMMERCIAL = "380"
CURRENCY_EUR = "EUR"
PAYMENT_SEPA_CREDIT_TRANSFER = "58"
TAX_SCHEME_VAT = "VAT"

# UBL 2.1
NS_UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"

VAT_CATEGORY_STANDARD = "S"
VAT_CATEGORY_ZERO = "Z"
VAT_CATEGORY_EXEMPT = "E"
VAT_CATEGORY_REVERSE = "AE"
VAT_CATEGORY_INTRA_COMMUNITY = "K"
VAT_CATEGORY_EXPORT = "G"
VAT_CATEGORY_NOT_SUBJECT = "O"

ZERO_TAX_CATEGORIES = frozenset(
    {
        VAT_CATEGORY_ZERO,
        VAT_CATEGORY_EXEMPT,
        VAT_CATEGORY_REVERSE,
        VAT_CATEGORY_INTRA_COMMUNITY,
        VAT_CATEGORY_EXPORT,
        VAT_CATEGORY_NOT_SUBJECT,
    }
)

DEFAULT_EXEMPTION = {
    "AE": ("VATEX-EU-AE", "Reverse Charge / Steuerschuldnerschaft des Leistungsempfängers"),
    "K": ("VATEX-EU-IC", "Innergemeinschaftliche Lieferung"),
    "G": ("VATEX-EU-G", "Export außerhalb der EU"),
    "E": ("VATEX-EU-AE", None),  # reason text required; code filled by caller when known
    "O": ("VATEX-EU-O", "Nicht steuerbar / outside scope of VAT"),
}

# Never emit these as a real USt-IdNr.
FORBIDDEN_VAT_PLACEHOLDERS = frozenset(
    {
        "",
        "TODO",
        "TBD",
        "XXX",
        "INSERT",
        "DE000000000",
        "DE1234567890",  # wrong length, often pasted as dummy
        "NONE",
        "NULL",
        "N/A",
        "NA",
    }
)

UNIT_PIECE = "C62"
UNIT_HOUR = "HUR"
UNIT_MONTH = "MON"

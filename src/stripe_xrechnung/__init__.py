"""stripe-xrechnung — Stripe Invoice JSON → XRechnung 3.0.2 UBL 2.1 (offline)."""

from stripe_xrechnung.constants import (
    LIB_VERSION,
    XRECHNUNG_VERSION,
    EN16931_YEAR,
    KOSIT_BUNDLE,
    XRECHNUNG_CUSTOMIZATION_ID,
)
from stripe_xrechnung.emit_ubl import emit_ubl
from stripe_xrechnung.map_stripe import map_stripe
from stripe_xrechnung.schema import CanonicalInvoice
from stripe_xrechnung.validate_local import validate_invoice

__version__ = LIB_VERSION

__all__ = [
    "LIB_VERSION",
    "XRECHNUNG_VERSION",
    "EN16931_YEAR",
    "KOSIT_BUNDLE",
    "XRECHNUNG_CUSTOMIZATION_ID",
    "CanonicalInvoice",
    "map_stripe",
    "emit_ubl",
    "validate_invoice",
    "__version__",
]

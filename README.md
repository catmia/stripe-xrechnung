# stripe-xrechnung

Stripe Invoice JSON → XRechnung 3.0.2 UBL 2.1, offline. Python ≥ 3.11. Dependencies: **pydantic** and **lxml**. No Stripe API calls, no Peppol access point, no network.

Search terms this library exists for: `stripe xrechnung`, Stripe Invoice to EN 16931 / XRechnung UBL.

## Scope

This repo is the mapper: Stripe Invoice JSON (or an `invoice.finalized` Event wrapper) → XRechnung 3.0.2 UBL 2.1 XML.

Out of scope here: ZUGFeRD / Factur-X CII, PDF/A-3, Peppol, the official KoSIT Java validator, LemonSqueezy, receive/archive.

## Disclaimer

**Not tax advice. Not legal advice.** You fill legal identity fields. **This library never invents a USt-IdNr (VAT ID).** Empty seller VAT stays empty; local validation then reports BR-DE-16 if a VAT category requires BT-31/BT-32. Local checks are structural + VAT math + a selected BR-DE subset. They are **not** the official KoSIT validator.

Kleinunternehmer remain **exempt from issuing** structured e-invoices under the current German mandate; **receiving is not exempt** (since 1 Jan 2025). This library will not pretend a Kleinunternehmer must issue XRechnung.

## Install

```bash
git clone https://github.com/catmia/stripe-xrechnung.git
cd stripe-xrechnung
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
stripe-xrechnung doctor
```

## 90-second demo

```bash
stripe-xrechnung emit fixtures/stripe_invoice.finalized.json -o /tmp/xrechnung.xml
```

Stripe does not ship seller VAT id or IBAN. Put them in a top-level `seller` object on the Invoice JSON, or pass `--seller seller.json`. The library **refuses to invent** a USt-IdNr.

## CLI

| Command | Job |
|---|---|
| `stripe-xrechnung emit FILE` | Stripe Invoice JSON → XRechnung 3.0.2 UBL XML |
| `stripe-xrechnung emit FILE --seller seller.json -o out.xml` | Same, with seller overlay |
| `stripe-xrechnung emit FILE --strict` | Fail (exit 2) on local validation errors |
| `stripe-xrechnung validate FILE` | Map then run local structural + VAT-math + selected BR-DE checks |
| `stripe-xrechnung doctor` | Spec pins, `network: disabled` |

`FILE` may be `-` (stdin). A Stripe Event wrapper (`invoice.finalized`) is unwrapped automatically.

Python API:

```python
from stripe_xrechnung import map_stripe, emit_ubl, validate_invoice
import json

payload = json.loads(open("invoice.json", encoding="utf-8").read())
invoice = map_stripe(payload)           # CanonicalInvoice
xml = emit_ubl(invoice)                 # bytes, UBL 2.1
report = validate_invoice(invoice)      # not KoSIT
```

## How Stripe Invoice JSON is mapped

Stripe amounts are **integer cents**. Dates are **Unix seconds** unless already ISO. Seller legal identity is **not** on a Stripe Invoice — overlay it. **Never invent a USt-IdNr.**

| Stripe field | Canonical / BT-* | Notes |
|---|---|---|
| `number` (fallback `id`) | `invoice_number` **BT-1** | Stripe `id` (`in_…`) only if `number` is still empty |
| `status_transitions.finalized_at` else `created` | `issue_date` **BT-2** | Unix → ISO date |
| *(fixed 380)* | `type_code` **BT-3** | Commercial invoice |
| `currency` | `currency` **BT-5** | `eur` → `EUR` |
| `due_date` | `due_date` **BT-9** | Unix → ISO |
| `metadata.leitweg_id` or `metadata.buyer_reference` | `buyer_reference` **BT-10** | **BR-DE-15 mandatory.** B2G: Leitweg-ID from the authority (do not guess). B2B: buyer reference / order number |
| `description` | `note` **BT-22** | Free text |
| `period_start` / `period_end` | `period_*` **BT-73/BT-74** | |
| `seller.name` or `metadata.seller_name` or `account_name` | seller name **BT-27** | Overlay. Prefer `seller` |
| `seller.street` / `city` / `postal_code` / `country` | seller address **BG-5** | Overlay |
| `seller.vat_id` / `metadata.seller_vat` | **BT-31** | **Never invented.** Empty stays empty |
| `seller.tax_number` | **BT-32** | Alternative to BT-31 in some DE cases |
| `seller.email` / `phone` / `contact_name` | **BT-43 / BT-42 / BT-41** | BR-DE-5/6/7 |
| `seller.email` as EndpointID scheme `EM` | **BT-34** | |
| `seller.iban` / `bic` / `account_name` | **BG-16** **BT-84/BT-86** | BR-DE-1. Means code `58` (SEPA credit transfer) |
| `customer_name` | buyer name **BT-44** | |
| `customer_address.line1/city/postal_code/country/state` | buyer address **BG-8** | |
| `customer_email` | buyer email / EndpointID **BT-49** | scheme `EM` |
| `customer_tax_ids[]` where `type=eu_vat` | buyer VAT **BT-48** | Also accepts Customer `tax_ids.data` |
| `lines.data[].description` | line name **BT-153** | |
| `lines.data[].quantity` | **BT-129** | |
| `lines.data[].price.recurring.interval` | unit **BT-130** | `month` → `MON`; else `C62` |
| `lines.data[].price.unit_amount` / 100 | net unit price **BT-146** | Exclusive tax expected |
| `lines.data[].amount` / 100 | line net **BT-131** | |
| `lines.data[].tax_amounts[].tax_rate.percentage` or `default_tax_rates[].percentage` | **BT-152 / BT-119** | DE typically 19 or 7 |
| `metadata.vat_category` | line `vat_category` | `S` `Z` `E` `AE` `K` `G` `O`. Default `S` |
| `metadata.exemption_reason` / `_code` | **BT-120 / BT-121** | Required for AE/K/G |
| `metadata.kleinunternehmer` | flag | Forces category E, tax 0, § 19 note. Does **not** invent a VAT id |
| `subtotal` / `tax` / `total` | cross-check only | Totals are **recomputed** with Decimal ROUND_HALF_UP (2 places) |

Seller overlay (`--seller` or top-level `seller`):

```json
{
  "name": "Beispiel GmbH",
  "street": "Musterstraße 1",
  "city": "Berlin",
  "postal_code": "10115",
  "country": "DE",
  "vat_id": "DE123456789",
  "email": "rechnung@beispiel.example",
  "phone": "+49-30-000000-0",
  "contact_name": "Ina Beispiel",
  "iban": "DE89370400440532013000",
  "bic": "COBADEFFXXX"
}
```

The `vat_id` above is a **textbook example**, not a live id. Put *your* id. Fixtures use Beispiel GmbH, textbook VAT ids, and IBANs labelled EXAMPLE.

What Stripe will never give you: seller USt-IdNr, Steuernummer, IBAN, Leitweg-ID, VAT categories K/AE/G with VATEX codes, Kleinunternehmer status. Those are master data.

## KoSIT goldens

Included UBL goldens `golden/xrechnung_b2b_19.xml` and `golden/xrechnung_b2g_leitweg.xml` were run through **KoSIT Validator 1.6.3** with the **XRechnung 3.0.2** configuration (bundle **2026-01-31**) on 2026-08-31 and assessed **ACCEPTABLE** (`valid="true"`). Pytest asserts emit output byte-equals those goldens. That is a pin of *this library's synthetic fixtures*, not a certificate that *your* invoices are valid. Run the official KoSIT validator on your data before sending.

## License

MIT — see [LICENSE](LICENSE). Commercial use of *generated invoices* is OK. The library does not claim copyright in your invoice data.

---

A fuller CLI (ZUGFeRD / Factur-X CII, archive, German error catalog) lives at https://vegasweiss.gumroad.com/l/e-rechnung-kit-2026

# Travis County Scraper — Full Field Expansion Design

**Goal:** Expand the pipeline from 3 CAD fields + 1 tax field to the complete 30+ field schema, add MLS check, and dedup by UID.

**Architecture:** Replace AG Grid UI scraping in cad_lookup.py with TrueProdigy API interception. Add direct-URL tax detail with receipts page. Add Bing-based MLS check. Expand all three models. Wire into pipeline.

**Tech Stack:** Python 3.11, Playwright async, pydantic v2, structlog, tenacity

---

## Investigation Results (confirmed live — 2026-06-18)

### CAD Endpoint
- Intercept: `searchfulltext` → all property fields in one JSON call
- UID field: `taxOfficeRef` (may be null) or `refID2` (always populated) — use `taxOfficeRef or refID2`
- Strip leading zero from 14-digit UID for business UID (13 digits)
- `deedDt` is in `/public/property/search` (fires on detail page, not searchfulltext)
- `/public/property/{pid}/deeds` → array of deeds, first entry = most recent = purchase date
- Both fire when navigating to `/property-detail/{pid}/{year}`
- Direct API call fails (auth required) — must use Playwright page interception

### Tax Assessor go2gov
- Detail URL: `showPropertyEntityDetail.do?account={UID_14_digit}&year={current_year}`
- Receipts URL: `showPaymentReceipts.do?account={UID_14_digit}` — table row 1 col 3 = last payment date
- Initial Delinquency Year: min of years_with_balance from existing extraction (no extra navigation)
- Prior Bill tab: JavaScript modal only (not a separate page) — delinquency year from tax table rows

### MLS
- Bing: `"{address} zillow OR redfin OR realtor"` — no bot detection
- Result = "Yes" if zillow/redfin/realtor in page body, else "No"

---

## Files Changed

| File | Change |
|---|---|
| `scraper/models.py` | Expand CADData (13 fields), TaxData (2 fields), ForeclosureRecord (20+ fields), to_sheet_row |
| `scraper/cad_lookup.py` | Complete rewrite — API interception, deeds endpoint, all fields |
| `scraper/tax_lookup.py` | Update — direct URL first, receipts page, expose delinquency year |
| `scraper/mls_lookup.py` | New — Bing search, return Yes/No |
| `scraper/google_sheets.py` | New column headers |
| `main.py` | Wire all new fields, add MLS step, dedup by UID |
| `tests/test_cad_lookup.py` | Update for new API interception + new fields |
| `tests/test_tax_lookup.py` | Update for new fields |
| `tests/test_mls_lookup.py` | New |
| `tests/test_main.py` | Update for new fields + MLS |

---

## Data Models

### CADData (expanded)
```python
class CADData(BaseModel):
    uid: Optional[str] = None                    # 13-digit (no leading zero)
    uid_raw: Optional[str] = None                # 14-digit (with leading zero, for URL construction)
    pid: Optional[str] = None                    # CAD internal property ID
    owner_name: Optional[str] = None
    owner_secondary: Optional[str] = None
    property_street: Optional[str] = None        # streetPrimary
    property_city: Optional[str] = None          # city / from fullSitus
    property_state: Optional[str] = None         # state
    property_zip: Optional[str] = None           # zip
    mailing_street: Optional[str] = None         # addrDeliveryLine
    mailing_city: Optional[str] = None           # addrCity
    mailing_state: Optional[str] = None          # addrState
    mailing_zip: Optional[str] = None            # addrZip
    appraised_value: Optional[str] = None        # appraisedValue
    property_type_code: Optional[str] = None     # propType ("R", "C", etc.)
    acreage: Optional[str] = None                # legalAcreage
    legal_description: Optional[str] = None      # legalDescription
    date_bought_by_owner: Optional[str] = None   # deedDt from /deeds endpoint (first result)
    property_status: Optional[str] = None        # active field
```

### TaxData (expanded)
```python
class TaxData(BaseModel):
    taxes_due: str = "0"
    years_delinquent: int = 0
    last_payment_date: Optional[str] = None      # from showPaymentReceipts.do
    initial_delinquency_year: Optional[str] = None  # min(years_with_balance)
```

### ForeclosureRecord (additions)
Add to existing model:
```python
    uid: Optional[str] = None
    owner_name_cad: Optional[str] = None
    owner_secondary: Optional[str] = None
    property_street: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    mailing_street: Optional[str] = None
    mailing_city: Optional[str] = None
    mailing_state: Optional[str] = None
    mailing_zip: Optional[str] = None
    property_type_code: Optional[str] = None
    acreage: Optional[str] = None
    legal_description_cad: Optional[str] = None
    date_bought_by_owner: Optional[str] = None
    years_delinquent: int = 0
    last_payment_date: Optional[str] = None
    initial_delinquency_year: Optional[str] = None
    listed_on_mls: Optional[str] = None          # "Yes" or "No"
```

---

## CAD Lookup — New Architecture

```
Search page → fill address → Enter
  ↓ intercept searchfulltext response
    → extract uid (taxOfficeRef or refID2), pid, owner, addresses, value, type, acreage, legal_desc
    → if no result and grantor given → retry with grantor name
    → if multiple results → use first result (closest address match)
  ↓ if pid found → navigate to property-detail/{pid}/{year}
    → intercept /public/property/{pid}/deeds
    → first deed in array = most recent purchase
    → deedDt = date_bought_by_owner
```

### UID construction
```python
uid_raw = data.get("taxOfficeRef") or data.get("refID2")   # "01070028210000"
uid = uid_raw.lstrip("0") if uid_raw else None              # "1070028210000"
```

---

## Tax Lookup — Updated Architecture

```
If uid_raw available:
  → URL: showPropertyEntityDetail.do?account={uid_raw}&year={current_year}
  → Extract: Total Due, years_delinquent, initial_delinquency_year (min of delinquent years)
  → Navigate to showPaymentReceipts.do?account={uid_raw}
  → Extract: last_payment_date (table row 1, column 3)
Else (no UID):
  → Fall back to existing address search
```

---

## MLS Lookup — New Component

```python
class MlsLookup:
    async def check(self, address: str) -> str:
        # Playwright on Bing
        # Query: "{address} zillow OR redfin OR realtor"
        # Return "Yes" if any of zillow/redfin/realtor in page body, else "No"
```

---

## Pipeline Changes (main.py)

1. After CAD lookup: wire uid, uid_raw, owner_name, addresses, appraised_value, type, acreage, legal_desc, date_bought
2. After tax lookup: wire years_delinquent, last_payment_date, initial_delinquency_year
3. Add MLS step: `mls_data = await mls.check(record.address)`
4. Before appending: dedup by UID (check existing_uids set loaded from sheets at startup)
5. Pass uid_raw from CAD to tax lookup (so tax uses UID directly)

---

## Dedup Logic

```python
# At pipeline start: load existing UIDs from sheet
existing_uids: set[str] = sheets.get_existing_uids()

# Before append:
if record.uid and record.uid in existing_uids:
    log.info("dedup_skip", uid=record.uid, instrument_no=record.instrument_no)
    continue
existing_uids.add(record.uid or "")
```

---

## Google Sheets Headers

New columns appended after existing columns (backward compatible):
uid, owner_name_cad, owner_secondary, property_street, property_city, property_state, property_zip, mailing_street, mailing_city, mailing_state, mailing_zip, property_type_code, acreage, legal_description_cad, date_bought_by_owner, years_delinquent, last_payment_date, initial_delinquency_year, listed_on_mls

---

## Success Criteria

- [ ] `python -m pytest tests/ -v` → all tests pass (42+ → 60+)
- [ ] CAD lookup returns uid, owner, addresses, value, legal_desc, purchase_date for real property
- [ ] Tax lookup returns total_due, last_payment_date, initial_delinquency_year for real property
- [ ] MLS lookup returns "Yes" or "No" for real address
- [ ] Pipeline deduplicates by UID
- [ ] Google Sheets has all new columns with correct headers

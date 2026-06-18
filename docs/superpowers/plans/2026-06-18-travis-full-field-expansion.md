# Travis County Full Field Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Travis County scraper from 3 enriched fields to the complete 30+ field schema — CAD API interception, Tax Assessor receipts, MLS check via Bing, UID-based dedup.

**Architecture:** Rewrite cad_lookup.py to intercept the TrueProdigy `searchfulltext` API (returns all property fields in one JSON call) plus the `/deeds` endpoint for purchase date. Update tax_lookup.py to use direct UID-based URL and scrape the receipts page for last payment date. Add mls_lookup.py using Playwright on Bing. Expand all three models and wire into the pipeline.

**Tech Stack:** Python 3.11, Playwright async, pydantic v2, structlog, tenacity

---

## File Map

| File | Action | What changes |
|---|---|---|
| `scraper/models.py` | Modify | Expand CADData (18 fields), TaxData (2 new fields), ForeclosureRecord (19 new fields), update `to_sheet_row()` |
| `scraper/cad_lookup.py` | Rewrite | TrueProdigy API interception + deeds endpoint, extract all fields |
| `scraper/tax_lookup.py` | Modify | Direct UID URL, receipts page scrape, expose initial_delinquency_year |
| `scraper/mls_lookup.py` | Create | Bing search Playwright scraper, returns "Yes"/"No" |
| `scraper/google_sheets.py` | Modify | New column headers, `get_existing_uids()` method |
| `main.py` | Modify | Wire all new fields, add MLS step, UID-based dedup |
| `tests/test_cad_lookup.py` | Rewrite | Tests for new API interception fields |
| `tests/test_tax_lookup.py` | Modify | Tests for new fields (last_payment_date, initial_delinquency_year) |
| `tests/test_mls_lookup.py` | Create | Tests for MLS Yes/No result |
| `tests/test_main.py` | Modify | Mock MLS lookup, assert new fields wired |

---

## Task 1: Expand Data Models

**Files:**
- Modify: `scraper/models.py`
- Modify: `tests/test_cad_lookup.py` (update field names)
- Modify: `tests/test_tax_lookup.py` (add new field assertions)

- [ ] **Step 1: Replace the 3 model classes in `scraper/models.py`**

Replace the entire content of `scraper/models.py` with:

```python
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class CADData(BaseModel):
    uid: Optional[str] = None                    # 13-digit, no leading zero (business key)
    uid_raw: Optional[str] = None                # 14-digit, with leading zero (for Tax URL)
    pid: Optional[str] = None                    # TrueProdigy internal property ID
    owner_name: Optional[str] = None             # name
    owner_secondary: Optional[str] = None        # nameSecondary
    property_street: Optional[str] = None        # streetPrimary e.g. "360 NUECES ST"
    property_city: Optional[str] = None          # city (from fullSitus parse)
    property_state: Optional[str] = None         # state
    property_zip: Optional[str] = None           # zip
    mailing_street: Optional[str] = None         # addrDeliveryLine
    mailing_city: Optional[str] = None           # addrCity
    mailing_state: Optional[str] = None          # addrState
    mailing_zip: Optional[str] = None            # addrZip
    appraised_value: Optional[str] = None        # appraisedValue (integer → string)
    property_type_code: Optional[str] = None     # propType: "R", "C", "M", etc.
    acreage: Optional[str] = None                # legalAcreage
    legal_description: Optional[str] = None      # legalDescription
    date_bought_by_owner: Optional[str] = None   # deedDt from /deeds first result
    property_status: Optional[str] = None        # active: "Yes"/"No"


class TaxData(BaseModel):
    taxes_due: str = "0"
    years_delinquent: int = 0
    last_payment_date: Optional[str] = None      # from showPaymentReceipts.do table
    initial_delinquency_year: Optional[str] = None  # earliest year with balance > 0


class ListingEntry(BaseModel):
    """Data captured from the clerk search results listing grid (before PDF download)."""
    instrument_no: str
    local_path: str
    date_filed: Optional[str] = None
    grantor_listing: Optional[str] = None
    sale_date_listing: Optional[str] = None
    legal_desc_listing: Optional[str] = None


class ForeclosureRecord(BaseModel):
    # --- Core PDF fields (existing) ---
    index_no: Optional[int] = None
    instrument_no: str
    address: str
    county: str = "Travis"
    sale_type: str = "Substitute Trustee Sale"
    sale_date: Optional[date] = None
    document_type: str = "Notice of Substitute Trustee Sale"
    grantor: str
    grantee: Optional[str] = None
    legal_description: Optional[str] = None
    related_document_no: Optional[str] = None
    related_doc_type: Optional[str] = "Deed of Trust"
    substitute_trustee: Optional[str] = None
    returnee_attorney: Optional[str] = None
    notary: Optional[str] = None
    date_received: Optional[date] = None
    pdf_link: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # --- Tax fields (existing, kept for backward compat) ---
    taxes_due: str = "0"
    appraised_value: Optional[str] = None
    account_number: Optional[str] = None         # uid_raw (14-digit), for sheet column compat
    property_status: Optional[str] = None
    # --- New: UID (primary key for dedup) ---
    uid: Optional[str] = None                    # 13-digit, no leading zero
    # --- New: CAD enrichment ---
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
    # --- New: Tax enrichment ---
    years_delinquent: int = 0
    last_payment_date: Optional[str] = None
    initial_delinquency_year: Optional[str] = None
    # --- New: MLS ---
    listed_on_mls: Optional[str] = None          # "Yes" or "No"

    def to_sheet_row(self) -> list:
        return [
            # Existing columns (A–W, backward compatible)
            self.index_no or "",
            self.instrument_no,
            self.address,
            self.county,
            self.sale_type,
            str(self.sale_date) if self.sale_date else "",
            self.document_type,
            self.grantor,
            self.grantee or "",
            self.legal_description or "",
            self.related_document_no or "",
            self.related_doc_type or "",
            self.substitute_trustee or "",
            self.returnee_attorney or "",
            self.notary or "",
            str(self.date_received) if self.date_received else "",
            self.pdf_link,
            self.property_status or "",
            self.account_number or "",
            self.created_at.isoformat(),
            self.updated_at.isoformat(),
            self.taxes_due,
            self.appraised_value or "",
            # New columns (X onward)
            self.uid or "",
            self.owner_name_cad or "",
            self.owner_secondary or "",
            self.property_street or "",
            self.property_city or "",
            self.property_state or "",
            self.property_zip or "",
            self.mailing_street or "",
            self.mailing_city or "",
            self.mailing_state or "",
            self.mailing_zip or "",
            self.property_type_code or "",
            self.acreage or "",
            self.legal_description_cad or "",
            self.date_bought_by_owner or "",
            str(self.years_delinquent),
            self.last_payment_date or "",
            self.initial_delinquency_year or "",
            self.listed_on_mls or "",
        ]


class RunReport(BaseModel):
    run_date: str
    date_range_searched: str
    total_results: int
    pdfs_downloaded: int
    records_processed: int
    required_field_extraction_rate: float
    cad_lookup_success_rate: float
    tax_lookup_success_rate: float
    failed_downloads: list[str]
    failed_cad_lookups: list[str]
    failed_tax_lookups: list[str]
    total_runtime_seconds: float

    @computed_field
    @property
    def overall_status(self) -> str:
        pdf_rate = self.pdfs_downloaded / max(self.total_results, 1)
        if (
            self.required_field_extraction_rate < 0.85
            or pdf_rate < 0.95
        ):
            return "FAIL"
        if (
            self.required_field_extraction_rate < 0.95
            or self.cad_lookup_success_rate < 0.90
            or self.tax_lookup_success_rate < 0.85
        ):
            return "REVIEW"
        return "PASS"
```

- [ ] **Step 2: Run existing tests to confirm they fail with the right errors**

```bash
cd d:/Scrapper && python -m pytest tests/test_cad_lookup.py tests/test_tax_lookup.py tests/test_main.py -v 2>&1 | head -60
```

Expected: failures on `account_number` field references (which no longer exist in CADData). This confirms the model change broke the old interface and we must update tests next.

- [ ] **Step 3: Update `tests/test_cad_lookup.py` for new CADData fields**

Replace entire file:

```python
import pytest
from unittest.mock import AsyncMock, patch
from scraper.cad_lookup import CADLookup
from scraper.models import CADData


@pytest.fixture
def config(tmp_path):
    from scraper.config import Config
    return Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="FOLDER123",
        google_credentials_path="config/credentials.json",
        google_token_path="config/token.json",
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )


def _mock_playwright_context(mock_pw_class):
    mock_pw = AsyncMock()
    mock_pw_class.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_class.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_browser = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_page = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()
    return mock_pw, mock_browser, mock_page


@pytest.mark.asyncio
async def test_lookup_returns_full_cad_data_on_success(config):
    lookup = CADLookup(config)
    mock_data = CADData(
        uid="1070028210000",
        uid_raw="01070028210000",
        pid="771190",
        owner_name="EMMICK RYAN",
        appraised_value="537655",
        property_street="360 NUECES ST",
        property_state="TX",
        property_zip="78701",
        property_status="Yes",
        date_bought_by_owner="2021-06-04",
    )

    with patch("scraper.cad_lookup.async_playwright") as mock_pw_class:
        _mock_playwright_context(mock_pw_class)
        with patch.object(lookup, "_search", new=AsyncMock(return_value=mock_data)):
            result = await lookup.lookup("360 Nueces ST 3301, Austin TX 78701", None)

    assert result.uid == "1070028210000"
    assert result.uid_raw == "01070028210000"
    assert result.owner_name == "EMMICK RYAN"
    assert result.appraised_value == "537655"
    assert result.date_bought_by_owner == "2021-06-04"


@pytest.mark.asyncio
async def test_lookup_falls_back_to_grantor_when_no_address_result(config):
    lookup = CADLookup(config)
    empty = CADData()
    mock_data = CADData(uid="1070028210000", owner_name="EMMICK RYAN")

    with patch("scraper.cad_lookup.async_playwright") as mock_pw_class:
        _mock_playwright_context(mock_pw_class)
        with patch.object(lookup, "_search", new=AsyncMock(side_effect=[empty, mock_data])):
            result = await lookup.lookup("", "EMMICK RYAN")

    assert result.uid == "1070028210000"


@pytest.mark.asyncio
async def test_lookup_returns_empty_cad_data_on_failure(config):
    lookup = CADLookup(config)

    with patch("scraper.cad_lookup.async_playwright") as mock_pw_class:
        _mock_playwright_context(mock_pw_class)
        with patch.object(lookup, "_search", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await lookup.lookup("360 Nueces ST", None)

    assert result is not None
    assert isinstance(result, CADData)
    assert result.uid is None
```

- [ ] **Step 4: Update `tests/test_tax_lookup.py` for new TaxData fields**

Replace entire file:

```python
import pytest
from unittest.mock import AsyncMock, patch
from scraper.tax_lookup import TaxLookup
from scraper.models import TaxData


@pytest.fixture
def config(tmp_path):
    from scraper.config import Config
    return Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="FOLDER123",
        google_credentials_path="config/credentials.json",
        google_token_path="config/token.json",
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )


@pytest.mark.asyncio
async def test_lookup_returns_delinquent_tax_with_payment_date(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(
        taxes_due="12500.00",
        years_delinquent=3,
        last_payment_date="01/15/2023",
        initial_delinquency_year="2021",
    )

    with patch.object(lookup, "_lookup_by_uid", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", "01090901290000")

    assert result.taxes_due == "12500.00"
    assert result.years_delinquent == 3
    assert result.last_payment_date == "01/15/2023"
    assert result.initial_delinquency_year == "2021"


@pytest.mark.asyncio
async def test_lookup_returns_zero_when_current(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="Current", years_delinquent=0, last_payment_date="12/31/2025")

    with patch.object(lookup, "_lookup_by_uid", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", "01090901290000")

    assert result.taxes_due == "Current"
    assert result.last_payment_date == "12/31/2025"


@pytest.mark.asyncio
async def test_lookup_falls_back_to_address_when_no_uid(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="5000.00", years_delinquent=1)

    with patch.object(lookup, "_search_by_address", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", None)

    assert result.taxes_due == "5000.00"


@pytest.mark.asyncio
async def test_lookup_returns_default_on_failure(config):
    lookup = TaxLookup(config)

    with patch.object(lookup, "_lookup_by_uid", new=AsyncMock(side_effect=Exception("timeout"))):
        with patch.object(lookup, "_search_by_address", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await lookup.lookup("1234 Oak St", "01090901290000")

    assert result.taxes_due == "0"
    assert isinstance(result, TaxData)
```

- [ ] **Step 5: Run tests — expect failures on missing methods `_lookup_by_uid`**

```bash
cd d:/Scrapper && python -m pytest tests/test_cad_lookup.py tests/test_tax_lookup.py -v 2>&1 | head -40
```

Expected: AttributeError on `_lookup_by_uid` (doesn't exist yet in TaxLookup). This confirms test targets the right interface. Proceed to Task 2.

- [ ] **Step 6: Commit model changes**

```bash
cd d:/Scrapper && git add scraper/models.py tests/test_cad_lookup.py tests/test_tax_lookup.py
git commit -m "feat: expand CADData, TaxData, ForeclosureRecord models for full field schema"
```

---

## Task 2: Rewrite CAD Lookup

**Files:**
- Rewrite: `scraper/cad_lookup.py`
- Test: `tests/test_cad_lookup.py` (already updated in Task 1)

- [ ] **Step 1: Replace entire `scraper/cad_lookup.py`**

```python
from __future__ import annotations
import asyncio
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import CADData
from scraper.logger import get_logger

log = get_logger("cad_lookup")

_SEARCH_URL = "https://travis.prodigycad.com/property-search"
_DETAIL_URL = "https://travis.prodigycad.com/property-detail/{pid}/2026"
_API_SEARCH  = "searchfulltext"
_API_DEEDS   = "/deeds"


class CADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, grantor: Optional[str]) -> CADData:
        query = address.strip() if address and address.strip() else ""
        if not query and not grantor:
            return CADData()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    result = await self._search(page, query) if query else CADData()
                    if not result.uid and grantor:
                        result = await self._search(page, grantor)
                    if result.pid and not result.date_bought_by_owner:
                        result.date_bought_by_owner = await self._get_deed_date(page, result.pid)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("cad_lookup_failed", address=address, error=str(exc))
            return CADData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search(self, page: Page, query: str) -> CADData:
        captured: dict = {}

        async def _on_response(response):
            if _API_SEARCH in response.url:
                try:
                    if "json" in response.headers.get("content-type", ""):
                        captured["data"] = await response.json()
                except Exception:
                    pass

        page.on("response", _on_response)

        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("#searchInput", timeout=20_000)
        except Exception:
            log.warning("cad_search_input_not_found")
            return CADData()

        await page.fill("#searchInput", query)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)

        page.remove_listener("response", _on_response)

        raw = captured.get("data", {})
        results = raw.get("results", [])
        if not results:
            log.info("cad_no_results", query=query)
            return CADData()

        # Use first result (best address match when multiple)
        rec = results[0] if isinstance(results, list) else results
        return _parse_cad_result(rec)

    async def _get_deed_date(self, page: Page, pid: str) -> Optional[str]:
        captured: dict = {}

        async def _on_response(response):
            if _API_DEEDS in response.url and str(pid) in response.url:
                try:
                    if "json" in response.headers.get("content-type", ""):
                        captured["data"] = await response.json()
                except Exception:
                    pass

        page.on("response", _on_response)
        detail_url = _DETAIL_URL.format(pid=pid)
        try:
            await page.goto(detail_url, wait_until="domcontentloaded")
            await asyncio.sleep(4)
        except Exception as exc:
            log.warning("cad_detail_nav_failed", pid=pid, error=str(exc))
        finally:
            page.remove_listener("response", _on_response)

        deeds = captured.get("data", {}).get("results", [])
        if deeds and isinstance(deeds, list):
            deed_dt = deeds[0].get("deedDt", "")
            if deed_dt:
                return deed_dt[:10]  # "2021-06-04 00:00:00" → "2021-06-04"
        return None


def _parse_cad_result(rec: dict) -> CADData:
    uid_raw = rec.get("taxOfficeRef") or rec.get("refID2") or ""
    uid = uid_raw.lstrip("0") if uid_raw else None

    appraised = rec.get("appraisedValue")
    appraised_str = str(int(appraised)) if appraised is not None else None

    # city: parse from fullSitus "360 NUECES ST, TX, 78701" or use addrCity fallback
    city = rec.get("city") or _parse_city_from_situs(rec.get("fullSitus", ""))

    return CADData(
        uid=uid or None,
        uid_raw=uid_raw or None,
        pid=str(rec.get("pid")) if rec.get("pid") else None,
        owner_name=rec.get("name") or None,
        owner_secondary=rec.get("nameSecondary") or None,
        property_street=rec.get("streetPrimary") or None,
        property_city=city or None,
        property_state=rec.get("state") or None,
        property_zip=rec.get("zip") or None,
        mailing_street=rec.get("addrDeliveryLine") or None,
        mailing_city=rec.get("addrCity") or None,
        mailing_state=rec.get("addrState") or None,
        mailing_zip=rec.get("addrZip") or None,
        appraised_value=appraised_str,
        property_type_code=rec.get("propType") or None,
        acreage=rec.get("legalAcreage") or None,
        legal_description=rec.get("legalDescription") or None,
        property_status=rec.get("active") or None,
        date_bought_by_owner=None,  # filled by _get_deed_date after search
    )


def _parse_city_from_situs(situs: str) -> Optional[str]:
    """'360 NUECES ST, AUSTIN, TX, 78701' → 'AUSTIN'. Handles missing city."""
    parts = [p.strip() for p in situs.split(",")]
    # Typical pattern: street, city, state+zip OR street, state, zip
    if len(parts) >= 3:
        candidate = parts[1]
        # Reject if it looks like a state abbreviation or zip
        if len(candidate) > 3 and not candidate.isdigit():
            return candidate
    return None
```

- [ ] **Step 2: Run CAD tests**

```bash
cd d:/Scrapper && python -m pytest tests/test_cad_lookup.py -v
```

Expected: all 3 CAD tests PASS.

- [ ] **Step 3: Run full suite to check for regressions**

```bash
cd d:/Scrapper && python -m pytest tests/ -v 2>&1 | tail -15
```

Expected: 42+ passed, 0 failed. (Some tests may need minor fixes if they referenced old `account_number` field on CADData — fix inline.)

- [ ] **Step 4: Commit**

```bash
cd d:/Scrapper && git add scraper/cad_lookup.py
git commit -m "feat: rewrite CAD lookup — TrueProdigy API interception, full field extraction, deeds endpoint"
```

---

## Task 3: Update Tax Lookup

**Files:**
- Modify: `scraper/tax_lookup.py`
- Test: `tests/test_tax_lookup.py` (already updated in Task 1)

- [ ] **Step 1: Replace `scraper/tax_lookup.py`**

```python
from __future__ import annotations
import asyncio
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import TaxData
from scraper.logger import get_logger

log = get_logger("tax_lookup")

_GO2GOV_BASE   = "https://travis.go2gov.net"
_DETAIL_URL    = _GO2GOV_BASE + "/showPropertyEntityDetail.do?account={uid}&year={year}"
_RECEIPTS_URL  = _GO2GOV_BASE + "/showPaymentReceipts.do?account={uid}"
_SEARCH_URL    = _GO2GOV_BASE + "/cart/responsive/search/displayQuickSearch.do?"
_SEL_INPUT     = "#qsfInput"
_SEL_SUBMIT    = "#qsfButtonSearch"
_SEL_RESULT    = "a[href*='showPropertyInfo.do']"
_SEL_TAX_ROWS  = "table tr"


class TaxLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, uid_raw: Optional[str]) -> TaxData:
        """
        uid_raw: 14-digit account number with leading zero (from CAD taxOfficeRef/refID2).
        address: fallback if uid_raw not available.
        """
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    if uid_raw:
                        return await self._lookup_by_uid(page, uid_raw)
                    return await self._search_by_address(page, address)
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("tax_lookup_failed", address=address, error=str(exc))
            return TaxData()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _lookup_by_uid(self, page: Page, uid_raw: str) -> TaxData:
        import datetime
        year = datetime.date.today().year
        detail_url = _DETAIL_URL.format(uid=uid_raw, year=year)
        log.info("tax_uid_lookup", url=detail_url)
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        result = await self._extract_from_detail_page(page)

        # Get last payment date from receipts page
        receipts_url = _RECEIPTS_URL.format(uid=uid_raw)
        try:
            await page.goto(receipts_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            result.last_payment_date = await self._extract_last_payment_date(page)
        except Exception as exc:
            log.warning("tax_receipts_failed", uid=uid_raw, error=str(exc))

        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_by_address(self, page: Page, address: str) -> TaxData:
        log.info("tax_address_search", address=address)
        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        await page.wait_for_selector(_SEL_INPUT, timeout=15_000)
        await page.fill(_SEL_INPUT, address)
        await asyncio.sleep(0.5)
        await page.click(_SEL_SUBMIT)
        await asyncio.sleep(4)
        try:
            await page.wait_for_selector(_SEL_RESULT, timeout=10_000)
        except Exception:
            log.warning("tax_no_results", address=address)
            return TaxData()
        best_link = await self._best_result_link(page, address)
        if not best_link:
            return TaxData()
        href = await best_link.get_attribute("href") or ""
        detail_url = href if href.startswith("http") else f"{_GO2GOV_BASE}{href}"
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        return await self._extract_from_detail_page(page)

    async def _best_result_link(self, page: Page, address: str):
        links = page.locator(_SEL_RESULT)
        count = await links.count()
        if count == 0:
            return None
        if count == 1:
            return links.first
        address_upper = address.upper().strip()
        best_el, best_score = None, -1
        for i in range(count):
            el = links.nth(i)
            try:
                td = el.locator("xpath=ancestor::td[1]")
                td_text = (await td.inner_text()).upper()
                score = _address_match_score(address_upper, td_text)
                if score > best_score:
                    best_score = score
                    best_el = el
            except Exception:
                continue
        return best_el if best_el is not None else links.first

    async def _extract_from_detail_page(self, page: Page) -> TaxData:
        try:
            await page.wait_for_selector(_SEL_TAX_ROWS, timeout=10_000)
        except Exception:
            log.warning("tax_no_table", url=page.url)
            return TaxData()

        rows = page.locator(_SEL_TAX_ROWS)
        total_rows = await rows.count()
        data_rows = total_rows - 1
        if data_rows <= 0:
            return TaxData(taxes_due="Current", years_delinquent=0)

        grand_total = 0.0
        years_with_balance: list[str] = []

        for i in range(1, total_rows):
            row = rows.nth(i)
            cells = row.locator("td")
            cell_count = await cells.count()
            if cell_count == 0:
                continue
            year_text  = (await cells.nth(0).inner_text()).strip()
            total_text = (await cells.nth(cell_count - 1).inner_text()).strip()
            amount     = _parse_amount(total_text)
            if amount > 0:
                grand_total += amount
                years_with_balance.append(year_text)
            elif i == 1 and amount == 0:
                return TaxData(taxes_due="Current", years_delinquent=0)

        taxes_due = f"{grand_total:.2f}" if grand_total > 0 else "Current"
        initial_year = min(years_with_balance) if years_with_balance else None

        log.info("tax_extracted", taxes_due=taxes_due, years_delinquent=len(years_with_balance))
        return TaxData(
            taxes_due=taxes_due,
            years_delinquent=len(years_with_balance),
            initial_delinquency_year=initial_year,
        )

    async def _extract_last_payment_date(self, page: Page) -> Optional[str]:
        """
        showPaymentReceipts.do table:
        Header: Receipt | Tax Year | Payment Date | Payment Amount
        First data row = most recent payment
        """
        try:
            await page.wait_for_selector(_SEL_TAX_ROWS, timeout=8_000)
            rows = page.locator(_SEL_TAX_ROWS)
            count = await rows.count()
            if count < 2:
                return None
            # Row index 1 = first data row (index 0 = header)
            first_data_row = rows.nth(1)
            cells = first_data_row.locator("td")
            cell_count = await cells.count()
            if cell_count >= 3:
                # Column index 2 = Payment Date
                date_text = (await cells.nth(2).inner_text()).strip()
                return date_text if date_text else None
        except Exception as exc:
            log.warning("tax_receipts_parse_failed", error=str(exc))
        return None


def _parse_amount(text: str) -> float:
    cleaned = text.replace(",", "").replace("$", "").strip()
    m = re.search(r"[\d]+(?:\.\d+)?", cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return 0.0


def _address_match_score(query: str, candidate: str) -> int:
    q_tokens = set(re.split(r"\W+", query))
    c_tokens = set(re.split(r"\W+", candidate))
    q_tokens.discard("")
    c_tokens.discard("")
    return len(q_tokens & c_tokens)
```

- [ ] **Step 2: Run tax tests**

```bash
cd d:/Scrapper && python -m pytest tests/test_tax_lookup.py -v
```

Expected: all 4 tax tests PASS.

- [ ] **Step 3: Run full suite**

```bash
cd d:/Scrapper && python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: 42+ passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
cd d:/Scrapper && git add scraper/tax_lookup.py
git commit -m "feat: tax lookup — direct UID URL, receipts page for last payment date, expose initial delinquency year"
```

---

## Task 4: Create MLS Lookup

**Files:**
- Create: `scraper/mls_lookup.py`
- Create: `tests/test_mls_lookup.py`

- [ ] **Step 1: Write failing test first**

Create `tests/test_mls_lookup.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from scraper.mls_lookup import MlsLookup


@pytest.fixture
def config(tmp_path):
    from scraper.config import Config
    return Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="FOLDER123",
        google_credentials_path="config/credentials.json",
        google_token_path="config/token.json",
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )


def _mock_playwright_context(mock_pw_class):
    mock_pw = AsyncMock()
    mock_pw_class.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_class.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_browser = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_page = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()
    return mock_pw, mock_browser, mock_page


@pytest.mark.asyncio
async def test_check_returns_yes_when_mls_sites_in_results(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        _, _, mock_page = _mock_playwright_context(mock_pw_class)
        mock_page.goto = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=(
            "zillow.com 123 Main St Austin TX Home for Sale $450,000 redfin listing"
        ))

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "Yes"


@pytest.mark.asyncio
async def test_check_returns_no_when_no_mls_sites(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        _, _, mock_page = _mock_playwright_context(mock_pw_class)
        mock_page.goto = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=(
            "Travis County Property Records 123 Main St deed transfer"
        ))

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "No"


@pytest.mark.asyncio
async def test_check_returns_no_on_failure(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        mock_pw = AsyncMock()
        mock_pw_class.return_value.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        mock_pw_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "No"


@pytest.mark.asyncio
async def test_check_empty_address_returns_no(config):
    lookup = MlsLookup(config)
    result = await lookup.check("")
    assert result == "No"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd d:/Scrapper && python -m pytest tests/test_mls_lookup.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError for `scraper.mls_lookup`. Confirms test targets the right module.

- [ ] **Step 3: Create `scraper/mls_lookup.py`**

```python
from __future__ import annotations
import asyncio
from playwright.async_api import async_playwright
from scraper.config import Config
from scraper.logger import get_logger

log = get_logger("mls_lookup")

_MLS_SITES = ["zillow", "redfin", "realtor"]


class MlsLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def check(self, address: str) -> str:
        if not address or not address.strip():
            return "No"
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    query = f"{address} zillow OR redfin OR realtor"
                    bing_url = "https://www.bing.com/search?q=" + query.replace(" ", "+")
                    await page.goto(bing_url, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    body = await page.evaluate("() => document.body.innerText")
                    body_lower = body.lower()
                    listed = any(site in body_lower for site in _MLS_SITES)
                    result = "Yes" if listed else "No"
                    log.info("mls_check", address=address, result=result)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("mls_check_failed", address=address, error=str(exc))
            return "No"
```

- [ ] **Step 4: Run MLS tests**

```bash
cd d:/Scrapper && python -m pytest tests/test_mls_lookup.py -v
```

Expected: all 4 MLS tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd d:/Scrapper && python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: 46+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
cd d:/Scrapper && git add scraper/mls_lookup.py tests/test_mls_lookup.py
git commit -m "feat: add MLS lookup via Bing search — returns Yes/No"
```

---

## Task 5: Update Google Sheets

**Files:**
- Modify: `scraper/google_sheets.py`

- [ ] **Step 1: Replace `scraper/google_sheets.py`**

```python
from __future__ import annotations
from datetime import datetime
from googleapiclient.discovery import build
from scraper.config import Config
from scraper.google_drive import load_credentials
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("google_sheets")

SHEET_RANGE = "Sheet1"

# Column A = index 0. New columns start at X (index 23).
_UID_COL_LETTER = "X"     # column 24 (0-indexed: 23)
_LAST_COL_LETTER = "AP"   # 42 columns total (23 existing + 19 new)


class GoogleSheetsWriter:
    HEADERS = [
        # Existing columns A–W (23 cols, indexes 0–22)
        "Index #", "Instrument No.", "Address", "County", "Sale Type",
        "Sale Date", "Document Type", "Grantor(s)", "Grantee(s)",
        "Legal Description", "Related Document No.", "Related Doc Type",
        "Substitute Trustee", "Returnee/Attorney", "Notary",
        "Date Received", "PDF Link", "Property Status", "Account Number",
        "Created At", "Updated At", "Taxes Due", "Appraised Value",
        # New columns X–AP (19 cols, indexes 23–41)
        "UID", "Owner Name (CAD)", "Owner Secondary",
        "Property Street", "Property City", "Property State", "Property Zip",
        "Mailing Street", "Mailing City", "Mailing State", "Mailing Zip",
        "Property Type Code", "Acreage", "Legal Description (CAD)",
        "Date Bought By Owner", "Years Delinquent",
        "Last Payment Date", "Initial Delinquency Year", "Listed on MLS",
    ]

    def __init__(self, config: Config) -> None:
        self.config = config
        creds = load_credentials(config)
        self.service = build("sheets", "v4", credentials=creds)

    def ensure_headers(self) -> None:
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!A1:{_LAST_COL_LETTER}1",
            )
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!A1",
                valueInputOption="RAW",
                body={"values": [self.HEADERS]},
            ).execute()
            log.info("sheet_headers_written")

    def get_existing_uids(self) -> set[str]:
        """Return set of UID values already in the sheet (column X = UID column)."""
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!{_UID_COL_LETTER}:{_UID_COL_LETTER}",
            )
            .execute()
        )
        rows = result.get("values", [])
        return {row[0] for row in rows if row and row[0]}

    def _get_existing_instrument_nos(self) -> list[str]:
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!B:B",
            )
            .execute()
        )
        rows = result.get("values", [])
        return [row[0] for row in rows if row]

    def _get_next_index(self) -> int:
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!A:A",
            )
            .execute()
        )
        rows = result.get("values", [])
        return max(len(rows), 1)

    def append_record(self, record: ForeclosureRecord) -> bool:
        existing_instruments = self._get_existing_instrument_nos()
        if record.instrument_no in existing_instruments:
            log.info("skipping_duplicate_instrument", instrument_no=record.instrument_no)
            return False

        record.index_no = self._get_next_index()
        record.updated_at = datetime.utcnow()

        self.service.spreadsheets().values().append(
            spreadsheetId=self.config.google_sheets_id,
            range=f"{SHEET_RANGE}!A:{_LAST_COL_LETTER}",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [record.to_sheet_row()]},
        ).execute()
        log.info("record_appended", instrument_no=record.instrument_no)
        return True
```

- [ ] **Step 2: Run full suite**

```bash
cd d:/Scrapper && python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: 46+ passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
cd d:/Scrapper && git add scraper/google_sheets.py
git commit -m "feat: expand Google Sheets headers to 42 columns, add get_existing_uids for UID dedup"
```

---

## Task 6: Wire Pipeline in main.py

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Update `tests/test_main.py` to mock MLS and assert new fields**

Replace entire file:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date


@pytest.mark.asyncio
async def test_run_pipeline_calls_all_steps(tmp_path):
    from scraper.config import Config
    config = Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="FOLDER123",
        google_credentials_path="config/credentials.json",
        google_token_path="config/token.json",
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )
    from scraper.models import ForeclosureRecord, CADData, TaxData, ListingEntry
    sample_record = ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Oak St",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )

    with (
        patch("main.ClerkScraper") as MockClerk,
        patch("main.PDFExtractor") as MockExtractor,
        patch("main.CADLookup") as MockCAD,
        patch("main.TaxLookup") as MockTax,
        patch("main.MlsLookup") as MockMls,
        patch("main.GoogleDriveUploader") as MockDrive,
        patch("main.GoogleSheetsWriter") as MockSheets,
        patch("main.Validator") as MockValidator,
    ):
        MockClerk.return_value.run = AsyncMock(
            return_value=[ListingEntry(
                instrument_no="2026012345",
                local_path=str(tmp_path / "2026012345.pdf"),
                grantor_listing="JOHN DOE",
                sale_date_listing="06/03/2026",
                legal_desc_listing="LOT 5, BLOCK 12, SUNSET HILLS",
            )]
        )
        MockExtractor.return_value.extract.return_value = sample_record
        MockCAD.return_value.lookup = AsyncMock(
            return_value=CADData(
                uid="1070028210000",
                uid_raw="01070028210000",
                owner_name="JOHN DOE",
                appraised_value="400000",
                property_status="Yes",
            )
        )
        MockTax.return_value.lookup = AsyncMock(
            return_value=TaxData(
                taxes_due="0",
                years_delinquent=0,
                last_payment_date="12/31/2025",
            )
        )
        MockMls.return_value.check = AsyncMock(return_value="No")
        MockDrive.return_value.upload.return_value = "https://drive.google.com/file/abc"
        MockSheets.return_value.append_record.return_value = True
        MockSheets.return_value.get_existing_uids.return_value = set()
        mock_report = MagicMock()
        mock_report.overall_status = "PASS"
        mock_report.model_dump.return_value = {"overall_status": "PASS"}
        MockValidator.return_value.build_run_report.return_value = mock_report

        import main
        report = await main.run_pipeline(config, run_date=date(2026, 5, 13))

    assert report is not None
    assert report.overall_status == "PASS"
    # Verify MLS was called
    MockMls.return_value.check.assert_awaited_once()
```

- [ ] **Step 2: Run test to see it fail**

```bash
cd d:/Scrapper && python -m pytest tests/test_main.py -v 2>&1 | head -30
```

Expected: FAIL — `MlsLookup` not imported in main.py yet.

- [ ] **Step 3: Replace `main.py`**

```python
from __future__ import annotations
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Optional

from scraper.cad_lookup import CADLookup
from scraper.clerk_scraper import ClerkScraper
from scraper.config import load_config, Config
from scraper.google_drive import GoogleDriveUploader
from scraper.google_sheets import GoogleSheetsWriter
from scraper.logger import get_logger, setup_logging
from scraper.mls_lookup import MlsLookup
from scraper.models import ForeclosureRecord, ListingEntry
from scraper.pdf_extractor import PDFExtractor
from scraper.tax_lookup import TaxLookup
from scraper.validator import Validator


def _normalize(s: str | None) -> str:
    return " ".join((s or "").upper().split())


def _cross_reference(record: ForeclosureRecord, entry: ListingEntry, log) -> None:
    """Compare clerk listing grid data vs PDF extraction. Listing is authoritative on conflict."""
    mismatches: list[str] = []

    if entry.grantor_listing:
        pdf_g = _normalize(record.grantor)
        listing_g = _normalize(entry.grantor_listing)
        if pdf_g and listing_g and pdf_g != listing_g:
            mismatches.append(f"grantor: pdf='{record.grantor}' listing='{entry.grantor_listing}'")
            record.grantor = entry.grantor_listing

    if entry.sale_date_listing:
        from datetime import datetime
        try:
            listing_sale = datetime.strptime(entry.sale_date_listing, "%m/%d/%Y").date()
            if record.sale_date and record.sale_date != listing_sale:
                mismatches.append(
                    f"sale_date: pdf='{record.sale_date}' listing='{listing_sale}'"
                )
            record.sale_date = listing_sale
        except ValueError:
            pass

    if entry.legal_desc_listing:
        pdf_ld = _normalize(record.legal_description)
        listing_ld = _normalize(entry.legal_desc_listing)
        if pdf_ld and listing_ld and pdf_ld != listing_ld:
            mismatches.append(
                f"legal_desc: pdf='{record.legal_description}' listing='{entry.legal_desc_listing}'"
            )
            record.legal_description = entry.legal_desc_listing

    if mismatches:
        log.warning("cross_ref_mismatch", instrument_no=record.instrument_no, mismatches=mismatches)
    else:
        log.info("cross_ref_ok", instrument_no=record.instrument_no)


async def run_pipeline(config: Config, run_date: Optional[date] = None) -> object:
    run_date = run_date or date.today()
    log = get_logger("orchestrator")
    setup_logging(config.logs_dir)
    start = time.monotonic()

    log.info("pipeline_start", run_date=str(run_date))

    clerk    = ClerkScraper(config)
    extractor = PDFExtractor()
    cad      = CADLookup(config)
    tax      = TaxLookup(config)
    mls      = MlsLookup(config)
    drive    = GoogleDriveUploader(config)
    sheets   = GoogleSheetsWriter(config)
    validator = Validator()

    sheets.ensure_headers()
    existing_uids: set[str] = sheets.get_existing_uids()

    listing_entries: list[ListingEntry] = []
    failed_downloads: list[str] = []
    try:
        listing_entries = await clerk.run(run_date)
    except Exception as exc:
        log.error("clerk_scraper_error", error=str(exc))

    log.info("pdfs_collected", count=len(listing_entries))

    records: list[ForeclosureRecord] = []
    cad_successes = 0
    tax_successes = 0
    failed_cad: list[str] = []
    failed_tax: list[str] = []

    for entry in listing_entries:
        instrument_no = entry.instrument_no
        local_path = entry.local_path
        try:
            drive_link = drive.upload(local_path, run_date)
            record = extractor.extract(local_path, pdf_link=drive_link)
            record.instrument_no = instrument_no

            _cross_reference(record, entry, log)

            # CAD enrichment
            try:
                cad_data = await cad.lookup(record.address, record.grantor)
                # Backward compat fields
                record.account_number = cad_data.uid_raw
                record.appraised_value = cad_data.appraised_value
                record.property_status = cad_data.property_status
                # New fields
                record.uid = cad_data.uid
                record.owner_name_cad = cad_data.owner_name
                record.owner_secondary = cad_data.owner_secondary
                record.property_street = cad_data.property_street
                record.property_city = cad_data.property_city
                record.property_state = cad_data.property_state
                record.property_zip = cad_data.property_zip
                record.mailing_street = cad_data.mailing_street
                record.mailing_city = cad_data.mailing_city
                record.mailing_state = cad_data.mailing_state
                record.mailing_zip = cad_data.mailing_zip
                record.property_type_code = cad_data.property_type_code
                record.acreage = cad_data.acreage
                record.legal_description_cad = cad_data.legal_description
                record.date_bought_by_owner = cad_data.date_bought_by_owner
                if cad_data.uid:
                    cad_successes += 1
                else:
                    failed_cad.append(record.address)
            except Exception as cad_exc:
                log.error("cad_step_failed", instrument_no=instrument_no, error=str(cad_exc))
                failed_cad.append(record.address)

            # Tax enrichment — pass uid_raw so tax lookup uses direct URL
            try:
                tax_data = await tax.lookup(record.address, record.account_number)
                record.taxes_due = tax_data.taxes_due
                record.years_delinquent = tax_data.years_delinquent
                record.last_payment_date = tax_data.last_payment_date
                record.initial_delinquency_year = tax_data.initial_delinquency_year
                tax_successes += 1
            except Exception as tax_exc:
                log.error("tax_step_failed", instrument_no=instrument_no, error=str(tax_exc))
                failed_tax.append(record.address)

            # MLS check
            try:
                mls_address = record.property_street or record.address
                record.listed_on_mls = await mls.check(mls_address)
            except Exception as mls_exc:
                log.error("mls_step_failed", instrument_no=instrument_no, error=str(mls_exc))
                record.listed_on_mls = "No"

            # Dedup by UID (cross-run)
            if record.uid and record.uid in existing_uids:
                log.info("dedup_skip", uid=record.uid, instrument_no=instrument_no)
                continue
            if record.uid:
                existing_uids.add(record.uid)

            sheets.append_record(record)
            records.append(record)

            # TODO: AirTable integration (Priority 0 upload)
            # Criteria TBD with client
            # airtable_writer.upload(record, priority=0)

        except Exception as exc:
            log.error("record_processing_failed", instrument_no=instrument_no, error=str(exc))
            failed_downloads.append(instrument_no)

    runtime = time.monotonic() - start
    from_date = date(run_date.year, run_date.month, 1).strftime("%m/%d/%Y")
    to_date = run_date.strftime("%m/%d/%Y")

    report = validator.build_run_report(
        run_date=str(run_date),
        date_range=f"{from_date} to {to_date}",
        total_found=len(listing_entries),
        downloaded=len(listing_entries) - len(failed_downloads),
        records=records,
        cad_successes=cad_successes,
        tax_successes=tax_successes,
        failed_downloads=failed_downloads,
        failed_cad=failed_cad,
        failed_tax=failed_tax,
        runtime_seconds=runtime,
    )

    log.info(
        "pipeline_complete",
        status=report.overall_status,
        records=len(records),
        runtime_seconds=round(runtime, 1),
    )
    _write_log_file(report, config.logs_dir, run_date)
    return report


def _write_log_file(report, logs_dir: str, run_date: date) -> None:
    Path(logs_dir).mkdir(exist_ok=True)
    log_path = Path(logs_dir) / f"run_{run_date.strftime('%Y%m%d')}.json"
    with open(log_path, "w") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)


if __name__ == "__main__":
    config = load_config()
    asyncio.run(run_pipeline(config))
```

- [ ] **Step 4: Run main test**

```bash
cd d:/Scrapper && python -m pytest tests/test_main.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
cd d:/Scrapper && python -m pytest tests/ -v 2>&1 | tail -15
```

Expected: 50+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
cd d:/Scrapper && git add main.py tests/test_main.py
git commit -m "feat: wire all new CAD/tax/MLS fields into pipeline, UID-based cross-run dedup"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run full test suite with verbose output**

```bash
cd d:/Scrapper && python -m pytest tests/ -v 2>&1
```

Expected: **50+ passed, 0 failed, 0 errors**.

- [ ] **Step 2: Verify model produces correct sheet row length**

```bash
cd d:/Scrapper && python -c "
from scraper.models import ForeclosureRecord
from datetime import date
r = ForeclosureRecord(instrument_no='X', address='123 Main', grantor='Doe', pdf_link='http://x')
row = r.to_sheet_row()
print(f'Sheet row length: {len(row)}')
print(f'Expected: 42')
assert len(row) == 42, f'FAIL: got {len(row)}'
print('PASS')
"
```

Expected: `Sheet row length: 42` and `PASS`.

- [ ] **Step 3: Verify Google Sheets headers count matches**

```bash
cd d:/Scrapper && python -c "
from scraper.google_sheets import GoogleSheetsWriter
print(f'Header count: {len(GoogleSheetsWriter.HEADERS)}')
assert len(GoogleSheetsWriter.HEADERS) == 42
print('PASS')
"
```

Expected: `Header count: 42` and `PASS`.

- [ ] **Step 4: Commit final verification**

```bash
cd d:/Scrapper && git add -A
git status
git commit -m "feat: Travis County full field expansion complete — 42 fields, CAD API interception, Tax receipts, MLS check, UID dedup" --allow-empty
```

---

## Success Criteria Checklist

```
[ ] python -m pytest tests/ → 50+ passed, 0 failed
[ ] CADData has uid, uid_raw, pid, owner_name, property_street, mailing_*, appraised_value, type_code, acreage, legal_desc, date_bought, status
[ ] TaxData has taxes_due, years_delinquent, last_payment_date, initial_delinquency_year
[ ] ForeclosureRecord.to_sheet_row() returns 42 columns
[ ] GoogleSheetsWriter.HEADERS has 42 entries
[ ] cad_lookup.py uses API interception (no AG Grid UI scraping)
[ ] tax_lookup.py uses direct UID URL when uid_raw available
[ ] mls_lookup.py exists and returns "Yes"/"No"
[ ] main.py imports MlsLookup and calls mls.check()
[ ] main.py deduplicates by UID using existing_uids set
[ ] main.py passes uid_raw to tax.lookup()
```

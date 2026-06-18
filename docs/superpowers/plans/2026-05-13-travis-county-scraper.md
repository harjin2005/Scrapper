# Travis County Foreclosure Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully automated daily pipeline that scrapes Travis County Clerk foreclosure notices, extracts 14 data fields from PDFs, cross-references Travis CAD + Tax Office, and populates a Google Sheet with deduplication.

**Architecture:** Async Python pipeline using Playwright for all browser automation (clerk portal, CAD lookup, tax lookup), pdfplumber for PDF text extraction, and Google API client libraries for Drive/Sheets. All components are independent modules wired together by a single orchestrator in `main.py`. Each module is independently testable with mocked or fixture-based dependencies.

**Tech Stack:** Python 3.11, Playwright (async), pdfplumber, google-api-python-client, google-auth, pydantic v2, tenacity, structlog, PyYAML, pytest, pytest-asyncio, pytest-mock

---

## File Map

| File | Responsibility |
|------|---------------|
| `scraper/models.py` | Pydantic models: ForeclosureRecord, CADData, TaxData, RunReport |
| `scraper/config.py` | Load/validate config.yaml + env vars |
| `scraper/logger.py` | structlog setup, returns bound logger |
| `scraper/pdf_extractor.py` | Extract 14 fields from a single PDF file path |
| `scraper/clerk_scraper.py` | Playwright: search tccsearch.org, paginate, download PDFs |
| `scraper/cad_lookup.py` | Playwright: look up property on travis.prodigycad.com |
| `scraper/tax_lookup.py` | Playwright: look up delinquent taxes at tax-office.traviscountytx.gov |
| `scraper/google_drive.py` | Upload PDF to Drive, return shareable link |
| `scraper/google_sheets.py` | Append rows to sheet, check for duplicate instrument numbers |
| `scraper/validator.py` | Validate ForeclosureRecord completeness, produce RunReport |
| `main.py` | Orchestrator: runs all steps, writes log summary |
| `scheduler_setup.py` | Register Windows Task Scheduler job |
| `config/config.yaml` | Runtime config: URLs, sheet ID, folder ID, schedule |
| `config/credentials_template.json` | Google OAuth2 template (no real keys) |
| `requirements.txt` | Pinned dependencies |
| `README.md` | Setup + usage instructions |

---

## Task 1: Project Scaffold, Models, and Config

**Files:**
- Create: `scraper/__init__.py`
- Create: `scraper/models.py`
- Create: `scraper/config.py`
- Create: `config/config.yaml`
- Create: `config/credentials_template.json`
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models and config**

Create `tests/test_models.py`:
```python
import pytest
from datetime import date
from scraper.models import ForeclosureRecord, CADData, TaxData, RunReport

def test_foreclosure_record_required_fields():
    record = ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Main St, Austin TX 78701",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )
    assert record.instrument_no == "2026012345"
    assert record.county == "Travis"
    assert record.sale_type == "Substitute Trustee Sale"
    assert record.document_type == "Notice of Substitute Trustee Sale"

def test_foreclosure_record_defaults():
    record = ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Main St",
        grantor="Jane Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )
    assert record.taxes_due == "0"
    assert record.property_status is None
    assert record.account_number is None
    assert record.appraised_value is None

def test_cad_data_model():
    cad = CADData(
        account_number="R123456",
        appraised_value="450000",
        property_status="Active",
    )
    assert cad.account_number == "R123456"

def test_tax_data_model():
    tax = TaxData(taxes_due="12500.00", years_delinquent=3)
    assert tax.taxes_due == "12500.00"

def test_run_report_pass_criteria():
    report = RunReport(
        run_date="2026-05-13",
        date_range_searched="05/01/2026 to 05/13/2026",
        total_results=10,
        pdfs_downloaded=10,
        records_processed=10,
        required_field_extraction_rate=0.98,
        cad_lookup_success_rate=0.95,
        tax_lookup_success_rate=0.90,
        failed_downloads=[],
        failed_cad_lookups=[],
        failed_tax_lookups=[],
        total_runtime_seconds=120.5,
    )
    assert report.overall_status == "PASS"

def test_run_report_fail_criteria():
    report = RunReport(
        run_date="2026-05-13",
        date_range_searched="05/01/2026 to 05/13/2026",
        total_results=10,
        pdfs_downloaded=9,
        records_processed=9,
        required_field_extraction_rate=0.80,
        cad_lookup_success_rate=0.70,
        tax_lookup_success_rate=0.60,
        failed_downloads=["2026099999"],
        failed_cad_lookups=["123 Main St"],
        failed_tax_lookups=["123 Main St"],
        total_runtime_seconds=95.0,
    )
    assert report.overall_status == "FAIL"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'scraper'`

- [ ] **Step 3: Create `scraper/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `scraper/models.py`**

```python
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class ForeclosureRecord(BaseModel):
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
    property_status: Optional[str] = None
    account_number: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    taxes_due: str = "0"
    appraised_value: Optional[str] = None

    def to_sheet_row(self) -> list:
        return [
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
        ]


class CADData(BaseModel):
    account_number: Optional[str] = None
    appraised_value: Optional[str] = None
    property_status: Optional[str] = None


class TaxData(BaseModel):
    taxes_due: str = "0"
    years_delinquent: int = 0


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

- [ ] **Step 5: Create `scraper/config.py`**

```python
from __future__ import annotations
import os
from pathlib import Path
import yaml
from pydantic import BaseModel


class Config(BaseModel):
    clerk_portal_url: str
    cad_url: str
    tax_url: str
    google_sheets_id: str
    google_drive_folder_id: str
    google_credentials_path: str
    google_token_path: str
    downloads_dir: str
    logs_dir: str
    search_doc_type: str = "NOTICE OF SUBSTITUTE TRUSTEE SALE"
    retry_attempts: int = 3
    request_timeout_ms: int = 30000
    headless: bool = True


_CONFIG: Config | None = None


def load_config(path: str | None = None) -> Config:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    config_path = path or os.environ.get(
        "SCRAPER_CONFIG", str(Path(__file__).parent.parent / "config" / "config.yaml")
    )
    with open(config_path) as f:
        data = yaml.safe_load(f)
    _CONFIG = Config(**data)
    return _CONFIG
```

- [ ] **Step 6: Create `config/config.yaml`**

```yaml
clerk_portal_url: "https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession"
cad_url: "https://travis.prodigycad.com/property-search"
tax_url: "https://tax-office.traviscountytx.gov/properties/taxes/account-search"
google_sheets_id: "YOUR_GOOGLE_SHEETS_ID_HERE"
google_drive_folder_id: "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE"
google_credentials_path: "config/credentials.json"
google_token_path: "config/token.json"
downloads_dir: "downloads"
logs_dir: "logs"
search_doc_type: "NOTICE OF SUBSTITUTE TRUSTEE SALE"
retry_attempts: 3
request_timeout_ms: 30000
headless: true
```

- [ ] **Step 7: Create `config/credentials_template.json`**

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": ["http://localhost"]
  }
}
```

- [ ] **Step 8: Create `requirements.txt`**

```
playwright==1.44.0
pdfplumber==0.11.1
pydantic==2.7.1
google-api-python-client==2.128.0
google-auth==2.29.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
tenacity==8.3.0
structlog==24.1.0
PyYAML==6.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
pytest-mock==3.14.0
```

- [ ] **Step 9: Install dependencies**

```bash
cd d:/Scrapper
pip install -r requirements.txt
playwright install chromium
```

- [ ] **Step 10: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_models.py -v
```
Expected: `5 passed`

- [ ] **Step 11: Commit**

```bash
cd d:/Scrapper
git init
git add scraper/__init__.py scraper/models.py scraper/config.py config/config.yaml config/credentials_template.json requirements.txt tests/__init__.py tests/test_models.py
git commit -m "feat: project scaffold with pydantic models and config"
```

---

## Task 2: Logger Setup

**Files:**
- Create: `scraper/logger.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_logger.py`:
```python
import structlog
from scraper.logger import get_logger

def test_get_logger_returns_bound_logger():
    log = get_logger("test_component")
    assert log is not None

def test_logger_has_component_context(capsys):
    import structlog.testing
    with structlog.testing.capture_logs() as cap_logs:
        log = get_logger("pdf_extractor")
        log.info("extraction_started", instrument_no="2026012345")
    assert len(cap_logs) == 1
    assert cap_logs[0]["component"] == "pdf_extractor"
    assert cap_logs[0]["instrument_no"] == "2026012345"
    assert cap_logs[0]["event"] == "extraction_started"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_logger.py -v
```
Expected: `ImportError: cannot import name 'get_logger'`

- [ ] **Step 3: Create `scraper/logger.py`**

```python
import structlog
import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(logs_dir: str = "logs") -> None:
    Path(logs_dir).mkdir(exist_ok=True)
    log_file = Path(logs_dir) / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(component: str) -> structlog.BoundLogger:
    return structlog.get_logger().bind(component=component)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_logger.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/logger.py tests/test_logger.py
git commit -m "feat: structlog logger with component binding"
```

---

## Task 3: PDF Extractor

**Files:**
- Create: `scraper/pdf_extractor.py`
- Create: `tests/test_pdf_extractor.py`
- Create: `tests/fixtures/` (directory for sample PDFs)

- [ ] **Step 1: Write failing tests**

Create `tests/test_pdf_extractor.py`:
```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from scraper.pdf_extractor import PDFExtractor

SAMPLE_PDF_TEXT = """
NOTICE OF SUBSTITUTE TRUSTEE SALE

Instrument No.: 2026012345

Property: Commonly known as 1234 Oak Street, Austin, Texas 78701

Legal Description: LOT 5, BLOCK 12, SUNSET HILLS SUBDIVISION, TRAVIS COUNTY, TEXAS

Grantor: JOHN A. DOE AND MARY B. DOE

Grantee/Beneficiary: WELLS FARGO BANK, N.A.

Original Note Amount: $285,000.00

Deed of Trust Recorded: March 15, 2018, Instrument No. 2018045678

Substitute Trustee: Mortgage Solutions LLC, 1111 Law St, Austin TX 78702

Attorney/Returnee: Smith & Jones LLP, 2222 Legal Ave, Austin TX 78703

Sale Date: The first Tuesday of June 2026, being June 2, 2026 at 10:00 AM

Sale Location: Travis County Courthouse, Austin, Texas

Filed Date: 05/10/2026
"""


@pytest.fixture
def extractor():
    return PDFExtractor()


@pytest.fixture
def mock_pdf_path(tmp_path):
    pdf_file = tmp_path / "2026012345_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")
    return str(pdf_file)


def test_extract_instrument_no(extractor):
    result = extractor._extract_instrument_no(SAMPLE_PDF_TEXT, "2026012345_NOTICE.pdf")
    assert result == "2026012345"


def test_extract_address(extractor):
    result = extractor._extract_address(SAMPLE_PDF_TEXT)
    assert "1234 Oak Street" in result
    assert "Austin" in result


def test_extract_grantor(extractor):
    result = extractor._extract_grantor(SAMPLE_PDF_TEXT)
    assert "JOHN A. DOE" in result


def test_extract_grantee(extractor):
    result = extractor._extract_grantee(SAMPLE_PDF_TEXT)
    assert "WELLS FARGO" in result


def test_extract_sale_date(extractor):
    result = extractor._extract_sale_date(SAMPLE_PDF_TEXT)
    assert result is not None
    assert result.year == 2026
    assert result.month == 6


def test_extract_legal_description(extractor):
    result = extractor._extract_legal_description(SAMPLE_PDF_TEXT)
    assert "LOT 5" in result
    assert "SUNSET HILLS" in result


def test_extract_original_loan_amount(extractor):
    result = extractor._extract_loan_amount(SAMPLE_PDF_TEXT)
    assert "285,000" in result


def test_extract_deed_of_trust_recording(extractor):
    result = extractor._extract_dot_recording_no(SAMPLE_PDF_TEXT)
    assert "2018045678" in result


def test_extract_substitute_trustee(extractor):
    result = extractor._extract_substitute_trustee(SAMPLE_PDF_TEXT)
    assert "Mortgage Solutions" in result


def test_extract_attorney(extractor):
    result = extractor._extract_attorney(SAMPLE_PDF_TEXT)
    assert "Smith & Jones" in result


def test_extract_all_fields_returns_record(extractor, mock_pdf_path):
    with patch("pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_PDF_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        record = extractor.extract(mock_pdf_path, pdf_link="https://drive.google.com/file/abc")

    assert record.instrument_no == "2026012345"
    assert record.address is not None
    assert record.grantor is not None
    assert record.sale_date is not None
    assert record.pdf_link == "https://drive.google.com/file/abc"


def test_extract_handles_missing_fields(extractor, mock_pdf_path):
    sparse_text = "NOTICE OF SUBSTITUTE TRUSTEE SALE\nInstrument No.: 2026099999\nGrantor: JANE DOE\n"
    with patch("pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sparse_text
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        record = extractor.extract(mock_pdf_path, pdf_link="https://drive.google.com/file/abc")

    assert record is not None
    assert record.instrument_no == "2026099999"
    assert record.address == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_pdf_extractor.py -v
```
Expected: `ImportError: cannot import name 'PDFExtractor'`

- [ ] **Step 3: Create `scraper/pdf_extractor.py`**

```python
from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from typing import Optional
import pdfplumber
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("pdf_extractor")

# Month name → number mapping
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class PDFExtractor:
    def extract(self, pdf_path: str, pdf_link: str) -> ForeclosureRecord:
        filename = Path(pdf_path).stem
        text = self._read_pdf_text(pdf_path)
        log.info("pdf_text_extracted", pdf_path=pdf_path, char_count=len(text))

        instrument_no = self._extract_instrument_no(text, filename)
        record = ForeclosureRecord(
            instrument_no=instrument_no,
            address=self._extract_address(text) or "",
            grantor=self._extract_grantor(text) or "",
            grantee=self._extract_grantee(text),
            legal_description=self._extract_legal_description(text),
            sale_date=self._extract_sale_date(text),
            substitute_trustee=self._extract_substitute_trustee(text),
            returnee_attorney=self._extract_attorney(text),
            related_document_no=self._extract_dot_recording_no(text),
            pdf_link=pdf_link,
        )
        log.info("record_extracted", instrument_no=instrument_no)
        return record

    def _read_pdf_text(self, pdf_path: str) -> str:
        pages_text: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
        return "\n".join(pages_text)

    def _extract_instrument_no(self, text: str, filename: str) -> str:
        # Try from text first
        patterns = [
            r"Instrument\s+No\.?\s*:?\s*(\d{8,12})",
            r"Document\s+No\.?\s*:?\s*(\d{8,12})",
            r"Inst\.?\s+No\.?\s*:?\s*(\d{8,12})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        # Fall back to filename
        m = re.match(r"(\d{8,12})", filename)
        if m:
            return m.group(1)
        return filename.split("_")[0]

    def _extract_address(self, text: str) -> Optional[str]:
        patterns = [
            r"[Cc]ommonly\s+known\s+as\s+([^\n]+)",
            r"[Pp]roperty\s+[Aa]ddress\s*:?\s*([^\n]+)",
            r"[Pp]roperty\s*:.*?([0-9]+\s+\w+[^\n,]+(?:,\s*\w+\s*,?\s*TX[^\n]*)?)",
            r"([0-9]+\s+[A-Z][A-Z\s]+(?:STREET|DRIVE|LANE|AVE|ROAD|BLVD|WAY|COURT|CIR|DR|ST|LN|RD|CT)[^\n,]*(?:,\s*AUSTIN[^\n]*)?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                addr = m.group(1).strip().rstrip(".")
                if len(addr) > 5:
                    return addr
        return None

    def _extract_grantor(self, text: str) -> Optional[str]:
        patterns = [
            r"[Gg]rantor\s*:?\s*([^\n]+)",
            r"[Tt]rustor\s*:?\s*([^\n]+)",
            r"[Oo]wner\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None

    def _extract_grantee(self, text: str) -> Optional[str]:
        patterns = [
            r"[Gg]rantee\s*:?\s*([^\n]+)",
            r"[Bb]eneficiary\s*:?\s*([^\n]+)",
            r"[Ll]ender\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None

    def _extract_legal_description(self, text: str) -> Optional[str]:
        patterns = [
            r"[Ll]egal\s+[Dd]escription\s*:?\s*([^\n]+(?:\n[^\n]+){0,2})",
            r"(LOT\s+\d+[,\s]+BLOCK\s+\d+[^\n]+)",
            r"(TRACT\s+\d+[^\n]+TRAVIS\s+COUNTY[^\n]*)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().replace("\n", " ")
                if len(val) > 5:
                    return val
        return None

    def _extract_sale_date(self, text: str) -> Optional[date]:
        # "June 2, 2026" or "June 2026"
        pat = r"(?:being\s+)?([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"
        for m in re.finditer(pat, text, re.IGNORECASE):
            month_name = m.group(1).lower()
            if month_name in MONTHS:
                try:
                    return date(int(m.group(3)), MONTHS[month_name], int(m.group(2)))
                except ValueError:
                    continue
        # "first Tuesday of June 2026"
        pat2 = r"(?:first|1st)\s+Tuesday.*?([A-Za-z]+)\s+(\d{4})"
        m = re.search(pat2, text, re.IGNORECASE)
        if m:
            month_name = m.group(1).lower()
            if month_name in MONTHS:
                return self._first_tuesday(int(m.group(2)), MONTHS[month_name])
        return None

    def _first_tuesday(self, year: int, month: int) -> date:
        from datetime import date as dt
        d = dt(year, month, 1)
        # weekday(): Monday=0, Tuesday=1
        days_until_tuesday = (1 - d.weekday()) % 7
        return dt(year, month, 1 + days_until_tuesday)

    def _extract_loan_amount(self, text: str) -> Optional[str]:
        patterns = [
            r"[Oo]riginal\s+[Nn]ote\s+[Aa]mount\s*:?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"[Oo]bligations?\s+[Ss]ecured\s*:?\s*\$?([\d,]+(?:\.\d{2})?)",
            r"[Nn]ote\s+[Aa]mount\s*:?\s*\$?([\d,]+(?:\.\d{2})?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _extract_dot_recording_no(self, text: str) -> Optional[str]:
        patterns = [
            r"[Dd]eed\s+of\s+[Tt]rust.*?[Ii]nstrument\s+[Nn]o\.?\s*(\d{8,12})",
            r"[Dd]eed\s+of\s+[Tt]rust.*?[Dd]ocument\s+[Nn]o\.?\s*(\d{8,12})",
            r"[Rr]ecorded.*?[Ii]nstrument\s+[Nn]o\.?\s*(\d{8,12})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                return m.group(1).strip()
        return None

    def _extract_substitute_trustee(self, text: str) -> Optional[str]:
        patterns = [
            r"[Ss]ubstitute\s+[Tt]rustee\s*:?\s*([^\n]+)",
            r"[Tt]rustee\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None

    def _extract_attorney(self, text: str) -> Optional[str]:
        patterns = [
            r"[Aa]ttorney\s*:?\s*([^\n]+)",
            r"[Rr]eturnee\s*:?\s*([^\n]+)",
            r"[Ll]aw\s+[Ff]irm\s*:?\s*([^\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip(",.")
                if len(val) > 2:
                    return val
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_pdf_extractor.py -v
```
Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/pdf_extractor.py tests/test_pdf_extractor.py
git commit -m "feat: PDF extractor with regex for 14 foreclosure fields"
```

---

## Task 4: Clerk Portal Scraper (Playwright)

**Files:**
- Create: `scraper/clerk_scraper.py`
- Create: `tests/test_clerk_scraper.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_clerk_scraper.py`:
```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from scraper.clerk_scraper import ClerkScraper

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
async def test_build_date_range_current_month():
    scraper = ClerkScraper.__new__(ClerkScraper)
    from datetime import date
    from_date, to_date = scraper._build_date_range(date(2026, 5, 13))
    assert from_date == "05/01/2026"
    assert to_date == "05/13/2026"

@pytest.mark.asyncio
async def test_build_date_range_first_of_month():
    scraper = ClerkScraper.__new__(ClerkScraper)
    from datetime import date
    from_date, to_date = scraper._build_date_range(date(2026, 5, 1))
    assert from_date == "05/01/2026"
    assert to_date == "05/01/2026"

@pytest.mark.asyncio
async def test_get_dated_folder_path():
    scraper = ClerkScraper.__new__(ClerkScraper)
    scraper.downloads_dir = "/tmp/downloads"
    from datetime import date
    path = scraper._get_dated_download_path(date(2026, 5, 13))
    assert path.endswith("2026-05-13")

@pytest.mark.asyncio
async def test_pdf_filename_format():
    scraper = ClerkScraper.__new__(ClerkScraper)
    filename = scraper._build_pdf_filename("2026012345")
    assert filename == "2026012345_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_clerk_scraper.py -v
```
Expected: `ImportError: cannot import name 'ClerkScraper'`

- [ ] **Step 3: Create `scraper/clerk_scraper.py`**

```python
from __future__ import annotations
import asyncio
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout
from scraper.config import Config
from scraper.logger import get_logger

log = get_logger("clerk_scraper")


class ClerkScraper:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.downloads_dir = config.downloads_dir

    def _build_date_range(self, run_date: date) -> tuple[str, str]:
        from_date = date(run_date.year, run_date.month, 1)
        return from_date.strftime("%m/%d/%Y"), run_date.strftime("%m/%d/%Y")

    def _get_dated_download_path(self, run_date: date) -> str:
        folder = Path(self.downloads_dir) / run_date.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def _build_pdf_filename(self, instrument_no: str) -> str:
        return f"{instrument_no}_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"

    async def run(self, run_date: Optional[date] = None) -> list[tuple[str, str]]:
        """Returns list of (instrument_no, local_pdf_path) tuples."""
        run_date = run_date or date.today()
        from_date, to_date = self._build_date_range(run_date)
        download_dir = self._get_dated_download_path(run_date)
        log.info("clerk_search_start", from_date=from_date, to_date=to_date)

        results: list[tuple[str, str]] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.config.headless)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            page.set_default_timeout(self.config.request_timeout_ms)

            try:
                await self._navigate_and_search(page, from_date, to_date)
                results = await self._collect_all_pages(page, download_dir)
            except Exception as exc:
                log.error("clerk_scraper_failed", error=str(exc))
                raise
            finally:
                await browser.close()

        log.info("clerk_search_done", total_pdfs=len(results))
        return results

    async def _navigate_and_search(self, page: Page, from_date: str, to_date: str) -> None:
        await page.goto(self.config.clerk_portal_url)
        log.info("portal_loaded")

        # Fill Document Type — try select first, then text input
        doc_type = self.config.search_doc_type
        try:
            await page.select_option("select[name*='DocType'], select[id*='DocType']", label=doc_type, timeout=5000)
        except Exception:
            await page.fill("input[name*='DocType'], input[id*='DocType']", doc_type)

        # Fill date range — field names vary; try common patterns
        date_from_selector = (
            "input[name*='DateFrom'], input[id*='DateFrom'], "
            "input[name*='FiledDateFrom'], input[id*='FiledDateFrom']"
        )
        date_to_selector = (
            "input[name*='DateTo'], input[id*='DateTo'], "
            "input[name*='FiledDateTo'], input[id*='FiledDateTo']"
        )
        await page.fill(date_from_selector, from_date)
        await page.fill(date_to_selector, to_date)

        await page.click("input[type='submit'], button[type='submit'], input[value*='Search']")
        await page.wait_for_load_state("networkidle")
        log.info("search_submitted", from_date=from_date, to_date=to_date)

    async def _collect_all_pages(self, page: Page, download_dir: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        page_num = 1
        while True:
            log.info("processing_results_page", page_num=page_num)
            page_results = await self._download_pdfs_on_page(page, download_dir)
            results.extend(page_results)

            # Try to navigate to next page
            next_btn = page.locator(
                "a:has-text('Next'), input[value='Next'], a[id*='Next'], a[aria-label*='next']"
            )
            if await next_btn.count() > 0:
                await next_btn.first.click()
                await page.wait_for_load_state("networkidle")
                page_num += 1
            else:
                break

        return results

    async def _download_pdfs_on_page(self, page: Page, download_dir: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        # Find all document links (instrument number links in results table)
        links = page.locator("table tr td a[href*='InstrumentNo'], table tr td a[href*='instrument']")
        count = await links.count()

        for i in range(count):
            link = links.nth(i)
            instrument_no = (await link.inner_text()).strip()
            if not instrument_no:
                continue
            try:
                local_path = await self._download_single_pdf(page, link, instrument_no, download_dir)
                if local_path:
                    results.append((instrument_no, local_path))
                    log.info("pdf_downloaded", instrument_no=instrument_no)
            except Exception as exc:
                log.error("pdf_download_failed", instrument_no=instrument_no, error=str(exc))

        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _download_single_pdf(
        self, page: Page, link, instrument_no: str, download_dir: str
    ) -> Optional[str]:
        filename = self._build_pdf_filename(instrument_no)
        dest_path = str(Path(download_dir) / filename)

        if Path(dest_path).exists():
            log.info("pdf_already_exists", instrument_no=instrument_no)
            return dest_path

        async with page.expect_download() as dl_info:
            await link.click()
        download = await dl_info.value
        await download.save_as(dest_path)
        return dest_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_clerk_scraper.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/clerk_scraper.py tests/test_clerk_scraper.py
git commit -m "feat: Playwright clerk portal scraper with pagination and retry"
```

---

## Task 5: Travis CAD Lookup

**Files:**
- Create: `scraper/cad_lookup.py`
- Create: `tests/test_cad_lookup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cad_lookup.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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

@pytest.mark.asyncio
async def test_lookup_returns_cad_data_on_success(config):
    lookup = CADLookup(config)
    mock_data = CADData(account_number="R123456", appraised_value="450000", property_status="Active")

    with patch.object(lookup, "_search_by_address", return_value=mock_data):
        result = await lookup.lookup("1234 Oak St, Austin TX 78701", None)

    assert result.account_number == "R123456"
    assert result.appraised_value == "450000"

@pytest.mark.asyncio
async def test_lookup_returns_empty_cad_data_on_failure(config):
    lookup = CADLookup(config)

    with patch.object(lookup, "_search_by_address", side_effect=Exception("timeout")):
        result = await lookup.lookup("1234 Oak St", None)

    assert result is not None
    assert isinstance(result, CADData)
    assert result.account_number is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_cad_lookup.py -v
```
Expected: `ImportError: cannot import name 'CADLookup'`

- [ ] **Step 3: Create `scraper/cad_lookup.py`**

```python
from __future__ import annotations
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import CADData
from scraper.logger import get_logger

log = get_logger("cad_lookup")


class CADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, grantor: Optional[str]) -> CADData:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    result = await self._search_by_address(page, address)
                    if result.account_number:
                        return result
                    if grantor:
                        result = await self._search_by_owner(page, grantor)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("cad_lookup_failed", address=address, error=str(exc))
            return CADData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_by_address(self, page: Page, address: str) -> CADData:
        await page.goto(self.config.cad_url)
        # Try address search input
        await page.fill("input[placeholder*='ddress'], input[name*='address'], input[id*='address']", address)
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_cad_data(page)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _search_by_owner(self, page: Page, owner: str) -> CADData:
        await page.goto(self.config.cad_url)
        await page.fill("input[placeholder*='wner'], input[name*='owner'], input[id*='owner']", owner)
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_cad_data(page)

    async def _extract_cad_data(self, page: Page) -> CADData:
        # Click first result if results list appears
        first_result = page.locator("table tr:nth-child(2) td a, .property-result a, .search-result a")
        if await first_result.count() > 0:
            await first_result.first.click()
            await page.wait_for_load_state("networkidle")

        account_number = await self._get_text(
            page,
            "[data-label*='Account'], td:has-text('Account') + td, .account-number",
        )
        appraised_value = await self._get_text(
            page,
            "[data-label*='Appraised'], [data-label*='Market'], td:has-text('Market Value') + td",
        )
        property_status = await self._get_text(
            page,
            "[data-label*='Status'], td:has-text('Status') + td",
        )
        log.info(
            "cad_data_extracted",
            account_number=account_number,
            appraised_value=appraised_value,
        )
        return CADData(
            account_number=account_number,
            appraised_value=appraised_value,
            property_status=property_status,
        )

    async def _get_text(self, page: Page, selector: str) -> Optional[str]:
        try:
            el = page.locator(selector).first
            if await el.count() > 0:
                text = (await el.inner_text()).strip()
                return text if text else None
        except Exception:
            pass
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_cad_lookup.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/cad_lookup.py tests/test_cad_lookup.py
git commit -m "feat: Travis CAD lookup with address and owner fallback"
```

---

## Task 6: Tax Office Lookup

**Files:**
- Create: `scraper/tax_lookup.py`
- Create: `tests/test_tax_lookup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tax_lookup.py`:
```python
import pytest
from unittest.mock import patch
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
async def test_lookup_returns_delinquent_tax(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="12500.00", years_delinquent=3)

    with patch.object(lookup, "_search_by_address", return_value=mock_data):
        result = await lookup.lookup("1234 Oak St, Austin TX 78701", None)

    assert result.taxes_due == "12500.00"
    assert result.years_delinquent == 3

@pytest.mark.asyncio
async def test_lookup_returns_zero_when_current(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="0", years_delinquent=0)

    with patch.object(lookup, "_search_by_address", return_value=mock_data):
        result = await lookup.lookup("1234 Oak St", None)

    assert result.taxes_due == "0"

@pytest.mark.asyncio
async def test_lookup_returns_zero_on_failure(config):
    lookup = TaxLookup(config)

    with patch.object(lookup, "_search_by_address", side_effect=Exception("connection refused")):
        result = await lookup.lookup("1234 Oak St", None)

    assert result.taxes_due == "0"
    assert isinstance(result, TaxData)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_tax_lookup.py -v
```
Expected: `ImportError: cannot import name 'TaxLookup'`

- [ ] **Step 3: Create `scraper/tax_lookup.py`**

```python
from __future__ import annotations
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import TaxData
from scraper.logger import get_logger

log = get_logger("tax_lookup")


class TaxLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, account_number: Optional[str]) -> TaxData:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    if account_number:
                        result = await self._search_by_account(page, account_number)
                        if result.taxes_due != "0":
                            return result
                    return await self._search_by_address(page, address)
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("tax_lookup_failed", address=address, error=str(exc))
            return TaxData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_by_address(self, page: Page, address: str) -> TaxData:
        await page.goto(self.config.tax_url)
        await page.fill(
            "input[placeholder*='ddress'], input[name*='address'], input[id*='address']",
            address,
        )
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_tax_data(page)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _search_by_account(self, page: Page, account_number: str) -> TaxData:
        await page.goto(self.config.tax_url)
        await page.fill(
            "input[placeholder*='ccount'], input[name*='account'], input[id*='account']",
            account_number,
        )
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_tax_data(page)

    async def _extract_tax_data(self, page: Page) -> TaxData:
        # Click first result if list shown
        first_result = page.locator("table tr:nth-child(2) td a, .property-result a")
        if await first_result.count() > 0:
            await first_result.first.click()
            await page.wait_for_load_state("networkidle")

        # Check for "no delinquent taxes" message
        no_taxes = page.locator("text=no delinquent, text=current, text=no taxes due")
        if await no_taxes.count() > 0:
            log.info("tax_current", no_delinquent=True)
            return TaxData(taxes_due="Current", years_delinquent=0)

        # Extract total taxes due
        taxes_text = await self._get_text(
            page,
            "[data-label*='Total'], td:has-text('Total Due') + td, .total-due, .amount-due",
        )
        years = 0
        if taxes_text:
            year_cells = page.locator("td.year, [data-label*='Year'], .delinquent-year")
            years = await year_cells.count()

        taxes_due = self._parse_amount(taxes_text) if taxes_text else "0"
        log.info("tax_data_extracted", taxes_due=taxes_due, years_delinquent=years)
        return TaxData(taxes_due=taxes_due, years_delinquent=years)

    def _parse_amount(self, text: str) -> str:
        m = re.search(r"\$?([\d,]+(?:\.\d{2})?)", text.replace(",", ""))
        if m:
            return m.group(1)
        return text.strip()

    async def _get_text(self, page: Page, selector: str) -> Optional[str]:
        try:
            el = page.locator(selector).first
            if await el.count() > 0:
                text = (await el.inner_text()).strip()
                return text if text else None
        except Exception:
            pass
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_tax_lookup.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/tax_lookup.py tests/test_tax_lookup.py
git commit -m "feat: tax office lookup with account number and address search"
```

---

## Task 7: Google Drive Integration

**Files:**
- Create: `scraper/google_drive.py`
- Create: `tests/test_google_drive.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_google_drive.py`:
```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from scraper.google_drive import GoogleDriveUploader

@pytest.fixture
def config(tmp_path):
    from scraper.config import Config
    creds = tmp_path / "creds.json"
    creds.write_text('{"installed": {"client_id": "x", "client_secret": "y", "redirect_uris": ["http://localhost"], "auth_uri": "https://a.com", "token_uri": "https://b.com"}}')
    return Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="ROOT_FOLDER_ID",
        google_credentials_path=str(creds),
        google_token_path=str(tmp_path / "token.json"),
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )

def test_build_drive_path_for_date():
    uploader = GoogleDriveUploader.__new__(GoogleDriveUploader)
    path = uploader._build_drive_path(date(2026, 5, 13))
    assert path == "My Drive/Scrapping Task/Task 4: Travis County/PDFs/2026-05-13"

def test_get_shareable_link_format():
    uploader = GoogleDriveUploader.__new__(GoogleDriveUploader)
    link = uploader._make_shareable_link("FILE_ID_123")
    assert "FILE_ID_123" in link
    assert "drive.google.com" in link

def test_upload_file_calls_drive_api(config, tmp_path):
    pdf_path = tmp_path / "2026012345_NOTICE.pdf"
    pdf_path.write_bytes(b"PDF content")

    mock_service = MagicMock()
    mock_service.files().create().execute.return_value = {"id": "UPLOADED_FILE_ID"}

    uploader = GoogleDriveUploader.__new__(GoogleDriveUploader)
    uploader.service = mock_service
    uploader.config = config

    with patch.object(uploader, "_get_or_create_folder", return_value="DATED_FOLDER_ID"):
        link = uploader.upload(str(pdf_path), date(2026, 5, 13))

    assert "UPLOADED_FILE_ID" in link
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_google_drive.py -v
```
Expected: `ImportError: cannot import name 'GoogleDriveUploader'`

- [ ] **Step 3: Create `scraper/google_drive.py`**

```python
from __future__ import annotations
import os
from datetime import date
from pathlib import Path
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from scraper.config import Config
from scraper.logger import get_logger

log = get_logger("google_drive")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]


def build_google_service(config: Config):
    creds = _load_credentials(config)
    return build("drive", "v3", credentials=creds)


def _load_credentials(config: Config) -> Credentials:
    creds = None
    token_path = config.google_token_path
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(config.google_credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


class GoogleDriveUploader:
    # Folder path inside Drive
    TASK_FOLDER_PATH = ["Scrapping Task", "Task 4: Travis County", "PDFs"]

    def __init__(self, config: Config) -> None:
        self.config = config
        self.service = build_google_service(config)

    def _build_drive_path(self, run_date: date) -> str:
        date_str = run_date.strftime("%Y-%m-%d")
        return f"My Drive/{'/'.join(self.TASK_FOLDER_PATH)}/{date_str}"

    def _make_shareable_link(self, file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

    def _get_or_create_folder(self, parent_id: str, folder_name: str) -> str:
        query = (
            f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=meta, fields="id").execute()
        return folder["id"]

    def upload(self, pdf_path: str, run_date: date) -> str:
        dated_folder_id = self._get_dated_folder(run_date)
        filename = Path(pdf_path).name
        file_metadata = {"name": filename, "parents": [dated_folder_id]}
        media = MediaFileUpload(pdf_path, mimetype="application/pdf")
        uploaded = (
            self.service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        file_id = uploaded["id"]
        # Make file readable by anyone with link
        self.service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
        link = self._make_shareable_link(file_id)
        log.info("pdf_uploaded_to_drive", filename=filename, file_id=file_id)
        return link

    def _get_dated_folder(self, run_date: date) -> str:
        parent_id = self.config.google_drive_folder_id
        for folder_name in self.TASK_FOLDER_PATH:
            parent_id = self._get_or_create_folder(parent_id, folder_name)
        date_folder = run_date.strftime("%Y-%m-%d")
        return self._get_or_create_folder(parent_id, date_folder)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_google_drive.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/google_drive.py tests/test_google_drive.py
git commit -m "feat: Google Drive uploader with folder hierarchy and shareable links"
```

---

## Task 8: Google Sheets Integration

**Files:**
- Create: `scraper/google_sheets.py`
- Create: `tests/test_google_sheets.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_google_sheets.py`:
```python
import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from scraper.google_sheets import GoogleSheetsWriter
from scraper.models import ForeclosureRecord

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

@pytest.fixture
def sample_record():
    return ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Oak St, Austin TX 78701",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )

def test_is_duplicate_returns_true_when_found(config):
    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    existing = ["INDEX", "2026012345", "2026012346"]
    assert writer._is_duplicate("2026012345", existing) is True

def test_is_duplicate_returns_false_when_new(config):
    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    existing = ["2026011111", "2026022222"]
    assert writer._is_duplicate("2026033333", existing) is False

def test_sheet_headers():
    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    headers = writer.HEADERS
    assert "Instrument No." in headers
    assert "Address" in headers
    assert "Taxes Due" in headers
    assert "Appraised Value" in headers
    assert len(headers) == 23

def test_append_new_record(config, sample_record):
    mock_service = MagicMock()
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [["Index #", "Instrument No."], ["1", "2026099999"]]
    }
    mock_service.spreadsheets().values().append().execute.return_value = {}

    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    writer.service = mock_service

    result = writer.append_record(sample_record)
    assert result is True

def test_skip_duplicate_record(config, sample_record):
    mock_service = MagicMock()
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [["Index #", "Instrument No."], ["1", "2026012345"]]
    }

    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    writer.service = mock_service

    result = writer.append_record(sample_record)
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_google_sheets.py -v
```
Expected: `ImportError: cannot import name 'GoogleSheetsWriter'`

- [ ] **Step 3: Create `scraper/google_sheets.py`**

```python
from __future__ import annotations
from datetime import datetime
from googleapiclient.discovery import build
from scraper.config import Config
from scraper.google_drive import _load_credentials
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("google_sheets")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

SHEET_RANGE = "Sheet1"


class GoogleSheetsWriter:
    HEADERS = [
        "Index #", "Instrument No.", "Address", "County", "Sale Type",
        "Sale Date", "Document Type", "Grantor(s)", "Grantee(s)",
        "Legal Description", "Related Document No.", "Related Doc Type",
        "Substitute Trustee", "Returnee/Attorney", "Notary",
        "Date Received", "PDF Link", "Property Status", "Account Number",
        "Created At", "Updated At", "Taxes Due", "Appraised Value",
    ]

    def __init__(self, config: Config) -> None:
        self.config = config
        creds = _load_credentials(config)
        self.service = build("sheets", "v4", credentials=creds)

    def ensure_headers(self) -> None:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.config.google_sheets_id, range=f"{SHEET_RANGE}!A1:W1")
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

    def _is_duplicate(self, instrument_no: str, existing: list[str]) -> bool:
        return instrument_no in existing

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
        # Subtract 1 for header row; if only header or empty, index = 1
        return max(len(rows), 1)

    def append_record(self, record: ForeclosureRecord) -> bool:
        existing = self._get_existing_instrument_nos()
        if self._is_duplicate(record.instrument_no, existing):
            log.info("skipping_duplicate", instrument_no=record.instrument_no)
            return False

        record.index_no = self._get_next_index()
        record.updated_at = datetime.utcnow()

        self.service.spreadsheets().values().append(
            spreadsheetId=self.config.google_sheets_id,
            range=f"{SHEET_RANGE}!A:W",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [record.to_sheet_row()]},
        ).execute()
        log.info("record_appended", instrument_no=record.instrument_no)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_google_sheets.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/google_sheets.py tests/test_google_sheets.py
git commit -m "feat: Google Sheets writer with duplicate detection and auto-indexing"
```

---

## Task 9: Data Validator

**Files:**
- Create: `scraper/validator.py`
- Create: `tests/test_validator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_validator.py`:
```python
import pytest
from datetime import date
from scraper.validator import Validator
from scraper.models import ForeclosureRecord

@pytest.fixture
def complete_record():
    return ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Oak St, Austin TX 78701",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )

@pytest.fixture
def incomplete_record():
    return ForeclosureRecord(
        instrument_no="2026099999",
        address="",
        grantor="",
        sale_date=None,
        pdf_link="https://drive.google.com/file/def",
    )

def test_validate_complete_record(complete_record):
    v = Validator()
    passed, missing = v.validate_required_fields(complete_record)
    assert passed is True
    assert len(missing) == 0

def test_validate_incomplete_record(incomplete_record):
    v = Validator()
    passed, missing = v.validate_required_fields(incomplete_record)
    assert passed is False
    assert "address" in missing or "grantor" in missing

def test_extraction_rate_calculation():
    v = Validator()
    records = [
        ForeclosureRecord(instrument_no="001", address="123 A St", grantor="Doe", sale_date=date(2026,6,3), pdf_link="https://x"),
        ForeclosureRecord(instrument_no="002", address="", grantor="", sale_date=None, pdf_link="https://y"),
    ]
    rate = v.calculate_extraction_rate(records)
    assert rate == 0.5

def test_full_run_report_generation():
    from scraper.models import RunReport
    v = Validator()
    report = v.build_run_report(
        run_date="2026-05-13",
        date_range="05/01/2026 to 05/13/2026",
        total_found=10,
        downloaded=10,
        records=[
            ForeclosureRecord(instrument_no=str(i), address=f"{i} St", grantor="Doe", sale_date=date(2026,6,3), pdf_link="https://x")
            for i in range(10)
        ],
        cad_successes=9,
        tax_successes=9,
        failed_downloads=[],
        failed_cad=["bad_address"],
        failed_tax=["bad_address"],
        runtime_seconds=88.0,
    )
    assert report.overall_status in ("PASS", "REVIEW", "FAIL")
    assert report.total_results == 10
    assert report.records_processed == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_validator.py -v
```
Expected: `ImportError: cannot import name 'Validator'`

- [ ] **Step 3: Create `scraper/validator.py`**

```python
from __future__ import annotations
from scraper.models import ForeclosureRecord, RunReport
from scraper.logger import get_logger

log = get_logger("validator")

REQUIRED_FIELDS = ["instrument_no", "address", "grantor", "sale_date", "pdf_link"]


class Validator:
    def validate_required_fields(self, record: ForeclosureRecord) -> tuple[bool, list[str]]:
        missing = []
        for field in REQUIRED_FIELDS:
            val = getattr(record, field, None)
            if not val:
                missing.append(field)
        return len(missing) == 0, missing

    def calculate_extraction_rate(self, records: list[ForeclosureRecord]) -> float:
        if not records:
            return 0.0
        passed = sum(1 for r in records if self.validate_required_fields(r)[0])
        return passed / len(records)

    def build_run_report(
        self,
        run_date: str,
        date_range: str,
        total_found: int,
        downloaded: int,
        records: list[ForeclosureRecord],
        cad_successes: int,
        tax_successes: int,
        failed_downloads: list[str],
        failed_cad: list[str],
        failed_tax: list[str],
        runtime_seconds: float,
    ) -> RunReport:
        extraction_rate = self.calculate_extraction_rate(records)
        cad_rate = cad_successes / max(downloaded, 1)
        tax_rate = tax_successes / max(downloaded, 1)

        report = RunReport(
            run_date=run_date,
            date_range_searched=date_range,
            total_results=total_found,
            pdfs_downloaded=downloaded,
            records_processed=len(records),
            required_field_extraction_rate=extraction_rate,
            cad_lookup_success_rate=cad_rate,
            tax_lookup_success_rate=tax_rate,
            failed_downloads=failed_downloads,
            failed_cad_lookups=failed_cad,
            failed_tax_lookups=failed_tax,
            total_runtime_seconds=runtime_seconds,
        )
        log.info(
            "run_report_built",
            status=report.overall_status,
            extraction_rate=extraction_rate,
            cad_rate=cad_rate,
            tax_rate=tax_rate,
        )
        return report
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_validator.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/validator.py tests/test_validator.py
git commit -m "feat: data validator with required field checks and run report generation"
```

---

## Task 10: Main Orchestrator

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_main.py`:
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
    from scraper.models import ForeclosureRecord
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
        patch("main.GoogleDriveUploader") as MockDrive,
        patch("main.GoogleSheetsWriter") as MockSheets,
        patch("main.Validator") as MockValidator,
    ):
        MockClerk.return_value.run = AsyncMock(
            return_value=[("2026012345", str(tmp_path / "2026012345.pdf"))]
        )
        MockExtractor.return_value.extract.return_value = sample_record
        MockCAD.return_value.lookup = AsyncMock(return_value=MagicMock(account_number=None, appraised_value=None, property_status=None))
        MockTax.return_value.lookup = AsyncMock(return_value=MagicMock(taxes_due="0", years_delinquent=0))
        MockDrive.return_value.upload.return_value = "https://drive.google.com/file/abc"
        MockSheets.return_value.append_record.return_value = True
        MockValidator.return_value.build_run_report.return_value = MagicMock(overall_status="PASS")

        import main
        report = await main.run_pipeline(config, run_date=date(2026, 5, 13))

    assert report is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/Scrapper
python -m pytest tests/test_main.py -v
```
Expected: `ImportError: cannot import name 'run_pipeline' from 'main'`

- [ ] **Step 3: Create `main.py`**

```python
from __future__ import annotations
import asyncio
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from scraper.cad_lookup import CADLookup
from scraper.clerk_scraper import ClerkScraper
from scraper.config import load_config, Config
from scraper.google_drive import GoogleDriveUploader
from scraper.google_sheets import GoogleSheetsWriter
from scraper.logger import get_logger, setup_logging
from scraper.models import ForeclosureRecord
from scraper.pdf_extractor import PDFExtractor
from scraper.tax_lookup import TaxLookup
from scraper.validator import Validator


async def run_pipeline(config: Config, run_date: Optional[date] = None) -> object:
    run_date = run_date or date.today()
    log = get_logger("orchestrator")
    setup_logging(config.logs_dir)
    start = time.monotonic()

    log.info("pipeline_start", run_date=str(run_date))

    clerk = ClerkScraper(config)
    extractor = PDFExtractor()
    cad = CADLookup(config)
    tax = TaxLookup(config)
    drive = GoogleDriveUploader(config)
    sheets = GoogleSheetsWriter(config)
    validator = Validator()

    sheets.ensure_headers()

    # Step 1: Download PDFs from clerk portal
    pdf_pairs: list[tuple[str, str]] = []
    failed_downloads: list[str] = []
    try:
        pdf_pairs = await clerk.run(run_date)
    except Exception as exc:
        log.error("clerk_scraper_error", error=str(exc))

    log.info("pdfs_collected", count=len(pdf_pairs))

    # Step 2: Process each PDF
    records: list[ForeclosureRecord] = []
    cad_successes = 0
    tax_successes = 0
    failed_cad: list[str] = []
    failed_tax: list[str] = []

    for instrument_no, local_path in pdf_pairs:
        try:
            # Upload PDF to Drive first to get link
            drive_link = drive.upload(local_path, run_date)

            # Extract data
            record = extractor.extract(local_path, pdf_link=drive_link)

            # CAD lookup
            try:
                cad_data = await cad.lookup(record.address, record.grantor)
                record.account_number = cad_data.account_number
                record.appraised_value = cad_data.appraised_value
                record.property_status = cad_data.property_status
                if cad_data.account_number:
                    cad_successes += 1
                else:
                    failed_cad.append(record.address)
            except Exception as cad_exc:
                log.error("cad_step_failed", instrument_no=instrument_no, error=str(cad_exc))
                failed_cad.append(record.address)

            # Tax lookup
            try:
                tax_data = await tax.lookup(record.address, record.account_number)
                record.taxes_due = tax_data.taxes_due
                if tax_data.taxes_due not in ("0", "Current"):
                    tax_successes += 1
                else:
                    tax_successes += 1  # current taxes = success
            except Exception as tax_exc:
                log.error("tax_step_failed", instrument_no=instrument_no, error=str(tax_exc))
                failed_tax.append(record.address)

            # Append to sheet
            sheets.append_record(record)
            records.append(record)

        except Exception as exc:
            log.error("record_processing_failed", instrument_no=instrument_no, error=str(exc))
            failed_downloads.append(instrument_no)

    runtime = time.monotonic() - start
    from_date = date(run_date.year, run_date.month, 1).strftime("%m/%d/%Y")
    to_date = run_date.strftime("%m/%d/%Y")

    report = validator.build_run_report(
        run_date=str(run_date),
        date_range=f"{from_date} to {to_date}",
        total_found=len(pdf_pairs),
        downloaded=len(pdf_pairs) - len(failed_downloads),
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

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/Scrapper
python -m pytest tests/test_main.py -v
```
Expected: `1 passed`

- [ ] **Step 5: Run full test suite**

```bash
cd d:/Scrapper
python -m pytest tests/ -v --tb=short
```
Expected: All tests pass (29+ total)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: main orchestrator wiring all pipeline steps"
```

---

## Task 11: Windows Task Scheduler Setup

**Files:**
- Create: `scheduler_setup.py`

- [ ] **Step 1: Create `scheduler_setup.py`**

```python
"""
Run this script once as Administrator to register the daily scraper job.
Usage: python scheduler_setup.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def register_task() -> None:
    python_exe = sys.executable
    script_path = str(Path(__file__).parent / "main.py")
    working_dir = str(Path(__file__).parent)

    # XML-based task for full control over schedule
    task_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T07:00:00</StartBoundary>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday/>
          <Tuesday/>
          <Wednesday/>
          <Thursday/>
          <Friday/>
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{script_path}"</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Hidden>false</Hidden>
  </Settings>
</Task>"""

    xml_path = Path(working_dir) / "task_definition.xml"
    xml_path.write_text(task_xml, encoding="utf-16")

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", "TravisCountyForeclosureScraper",
         "/XML", str(xml_path), "/F"],
        capture_output=True,
        text=True,
    )
    xml_path.unlink(missing_ok=True)

    if result.returncode == 0:
        print("Task registered: TravisCountyForeclosureScraper")
        print("Runs: Mon-Fri at 07:00 AM")
    else:
        print(f"Registration failed: {result.stderr}")
        print("Run this script as Administrator.")
        sys.exit(1)


if __name__ == "__main__":
    register_task()
```

- [ ] **Step 2: Verify scheduler script is valid Python**

```bash
cd d:/Scrapper
python -c "import scheduler_setup; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scheduler_setup.py
git commit -m "feat: Windows Task Scheduler registration for daily Mon-Fri runs"
```

---

## Task 12: README and Final Tests

**Files:**
- Create: `README.md`
- Create: `tests/__init__.py` (ensure exists)

- [ ] **Step 1: Create `README.md`**

```markdown
# Travis County Foreclosure Scraper

Automated daily pipeline that scrapes Travis County Clerk foreclosure notices, extracts property data, cross-references Travis CAD and Tax Office, and updates a Google Sheet.

## Requirements

- Python 3.11+
- Google Cloud project with Drive API + Sheets API enabled
- Google OAuth2 credentials (Desktop app type)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Google API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable "Google Drive API" and "Google Sheets API"
3. Create OAuth2 credentials → Desktop app → Download as JSON
4. Copy to `config/credentials.json`

### 3. Configure

Edit `config/config.yaml`:

```yaml
google_sheets_id: "1ABC..."     # from Sheet URL: /spreadsheets/d/{ID}/edit
google_drive_folder_id: "0ABC..." # from Drive folder URL: /folders/{ID}
```

### 4. First run (OAuth consent)

```bash
python main.py
```

A browser window opens for Google sign-in. After approval, `config/token.json` is saved. All subsequent runs are unattended.

### 5. Schedule (Windows)

Run once as Administrator:

```bash
python scheduler_setup.py
```

Registers "TravisCountyForeclosureScraper" in Task Scheduler — runs Mon-Fri at 7:00 AM.

## Manual run

```bash
python main.py
```

## Run tests

```bash
python -m pytest tests/ -v
```

## Output

- **Google Sheet**: `My Drive/Scrapping Task/Task 4: Travis County/travis_county_foreclosures`
- **PDFs**: `My Drive/Scrapping Task/Task 4: Travis County/PDFs/YYYY-MM-DD/`
- **Logs**: `logs/run_YYYYMMDD.json`

## Acceptance criteria

| Metric | Target |
|--------|--------|
| Required field extraction | ≥95% |
| PDF download success | 100% |
| Travis CAD lookup success | ≥90% |
| Tax Office lookup success | ≥85% |
| Duplicate records | 0 |
```

- [ ] **Step 2: Run complete test suite**

```bash
cd d:/Scrapper
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: `X passed, 0 failed` (29+ tests)

- [ ] **Step 3: Final commit**

```bash
git add README.md tests/__init__.py
git commit -m "docs: README with setup, configuration, and usage instructions"
```

---

## Spec Coverage Check

| Requirement | Task |
|-------------|------|
| Search tccsearch.org for NOTICE OF SUBSTITUTE TRUSTEE SALE | Task 4 |
| Date range: first day of month to current date | Task 4 |
| Download all PDFs | Task 4 |
| Handle pagination | Task 4 |
| PDF naming convention | Task 4 |
| Extract 14 fields from PDF | Task 3 |
| Travis CAD lookup (address, owner fallback) | Task 5 |
| Tax Office lookup (address, account fallback) | Task 6 |
| Google Drive folder structure with dates | Task 7 |
| Google Sheets: 23 columns in correct order | Task 8 |
| Deduplication by Instrument No. | Task 8 |
| Validation: PASS/REVIEW/FAIL thresholds | Task 9 |
| Daily Mon-Fri scheduling | Task 11 |
| Logging: date range, counts, failures, runtime | Task 10 |
| Retry failed downloads 3 times | Task 4 |
| CAPTCHA note in README | Task 12 |
| requirements.txt | Task 1 |
| README with setup | Task 12 |
| config template | Task 1 |

All 19 requirements covered. No gaps.

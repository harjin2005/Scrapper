# Travis County Foreclosure Scraper

**Production-grade daily pipeline** that monitors Travis County Clerk filings, downloads foreclosure PDFs, extracts 14 structured fields, cross-references Travis CAD and Tax Office, and delivers enriched records to Google Sheets — fully automated, zero manual steps.

---

## What It Does

Every weekday at 7:00 AM the system:

1. Opens Travis County Clerk portal (`tccsearch.org`) and submits a date-ranged search for *Notice of Substitute Trustee Sale* documents filed in the current month
2. Downloads every matching PDF (handles 4+ pages of results, skips already-downloaded files)
3. Extracts 14 structured fields from each PDF using multi-strategy parsing (regex, OCR fallback for scanned documents)
4. Looks up each property on Travis Central Appraisal District for appraised value and account number
5. Looks up delinquent taxes at Travis County Tax Office
6. Uploads each PDF to Google Drive under a dated folder hierarchy
7. Appends new records to Google Sheets with deduplication (instrument number as key) — never overwrites existing data
8. Writes a JSON run log with field extraction rates, CAD/tax success rates, and PASS/REVIEW/FAIL status

---

## Architecture

```
Windows Task Scheduler (Mon–Fri 7:00 AM)
        │
        ▼
   main.py  ─────────────── async orchestrator
        │
        ├─► ClerkScraper       Playwright + Chrome CDP
        │     • Cloudflare bypass via real Chrome profile copy
        │     • ASP.NET form submission (date range + doc type)
        │     • Paginated results (pg=N URL pattern)
        │     • PDF download via CDP Fetch.enable intercept
        │
        ├─► PDFExtractor        pdfplumber + PyMuPDF + pytesseract
        │     • Text PDFs: direct pdfplumber extraction
        │     • Scanned PDFs: OCR fallback (300 DPI render → tesseract)
        │     • 6 regex pattern families per field, priority-ordered
        │     • Handles: residential, commercial WHEREAS, two-column
        │       table layout, HOA/condo Notice of Sale
        │
        ├─► CADLookup           Playwright (travis.prodigycad.com)
        │     • Primary: address search
        │     • Fallback: owner name (grantor)
        │
        ├─► TaxLookup           Playwright (tax-office.traviscountytx.gov)
        │     • Primary: address search
        │     • Fallback: CAD account number
        │
        ├─► GoogleDriveUploader google-api-python-client
        │     • Folder path: My Drive/Scrapping Task/Task 4: Travis County/PDFs/YYYY-MM-DD/
        │     • Returns shareable Drive link per PDF
        │
        ├─► GoogleSheetsWriter  google-api-python-client
        │     • Dedup: instrument number checked against existing rows
        │     • Appends 23 columns in client-specified order
        │
        └─► Validator           pydantic v2
              • PASS / REVIEW / FAIL thresholds per spec
              • JSON run report written to logs/run_YYYYMMDD.json
```

### Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Browser automation | Playwright (async) + Chrome CDP | tccsearch.org uses ASP.NET with Cloudflare; real Chrome profile bypasses bot detection |
| PDF extraction | pdfplumber + PyMuPDF + pytesseract | pdfplumber handles native text PDFs; OCR fallback for scanned county documents |
| Data models | Pydantic v2 | Strict field validation, clean serialisation to Sheets |
| Google APIs | google-api-python-client (OAuth2) | Official library; token auto-refresh, no re-auth after first run |
| Retry logic | tenacity | 3-attempt exponential backoff on PDF downloads and API calls |
| Logging | structlog | Structured JSON log lines, component-bound context |
| Scheduling | Windows Task Scheduler | Native, no external dependencies; runs as SYSTEM at highest privilege |

---

## Setup

### Prerequisites

- Windows 10/11
- Python 3.10+
- Google Chrome installed at default path (`C:\Program Files\Google\Chrome\Application\chrome.exe`)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — required for scanned PDFs. Install the Windows installer, accept the default install path (`C:\Program Files\Tesseract-OCR\`), and ensure `tesseract` is on the system PATH.
- Google Cloud project with **Drive API** and **Sheets API** enabled

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Google API credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → **APIs & Services** → **Enable APIs**
3. Enable: **Google Drive API** and **Google Sheets API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID** → Desktop app
5. Download the JSON file → rename to `credentials.json` → place in `config/`

### 3. Configure IDs

Edit `config/config.yaml`:

```yaml
google_sheets_id: "1ABC..."        # from Sheet URL: /spreadsheets/d/{ID}/edit
google_drive_folder_id: "0ABC..."  # from Drive folder URL: /folders/{ID}
```

The Google Sheet should match this Drive path:
`My Drive / Scrapping Task / Task 4: Travis County / travis_county_foreclosures`

The Drive folder should be:
`My Drive / Scrapping Task / Task 4: Travis County / PDFs`

### 4. First run — authorize Google APIs

```bash
python main.py
```

A browser window opens for Google sign-in. Approve access once. `config/token.json` is saved and reused for all future runs — no re-authentication required.

### 5. Register Task Scheduler (run as Administrator)

Open **Command Prompt as Administrator**, then:

```bash
python D:\Scrapper\scheduler_setup.py
```

This registers **TravisCountyForeclosureScraper** in Windows Task Scheduler:
- Schedule: Mon–Fri at 7:00 AM
- Action: `D:\Scrapper\run_scraper.bat`
- Privilege: Highest (SYSTEM account)

To verify: open **Task Scheduler** → **Task Scheduler Library** → find `TravisCountyForeclosureScraper`

### 6. Verify the task

```bash
python -m pytest tests/ -v
```

All tests pass on the included test data before deployment.

---

## Running Manually

```bash
python main.py
```

Output appears in the terminal. A full run for ~80 PDFs takes 40–60 minutes (Playwright CAD + tax lookups are the bottleneck).

---

## Output

| Output | Location |
|--------|----------|
| Google Sheet | `My Drive/Scrapping Task/Task 4: Travis County/travis_county_foreclosures` |
| PDFs | `My Drive/Scrapping Task/Task 4: Travis County/PDFs/YYYY-MM-DD/` |
| Run logs | `logs/run_YYYYMMDD.json` |
| Local PDF cache | `downloads/YYYY-MM-DD/` |

### Google Sheet — 23 columns

| # | Column | Source |
|---|--------|--------|
| 1 | Index # | Auto-incremented |
| 2 | Instrument No. | Clerk portal |
| 3 | Address | PDF extraction |
| 4 | County | Fixed: "Travis" |
| 5 | Sale Type | Fixed: "Substitute Trustee Sale" |
| 6 | Sale Date | PDF extraction |
| 7 | Document Type | Fixed: "Notice of Substitute Trustee Sale" |
| 8 | Grantor(s) | PDF extraction |
| 9 | Grantee(s) | PDF extraction |
| 10 | Legal Description | PDF extraction |
| 11 | Related Document No. | PDF extraction |
| 12 | Related Doc Type | Fixed: "Deed of Trust" |
| 13 | Substitute Trustee | PDF extraction |
| 14 | Returnee/Attorney | PDF extraction |
| 15 | Notary | PDF extraction |
| 16 | Date Received | PDF extraction |
| 17 | PDF Link | Google Drive shareable link |
| 18 | Property Status | Travis CAD |
| 19 | Account Number | Travis CAD |
| 20 | Created At | Run timestamp |
| 21 | Updated At | Run timestamp |
| 22 | Taxes Due | Travis County Tax Office |
| 23 | Appraised Value | Travis CAD |

---

## Validation & Quality Thresholds

Per the project specification:

| Metric | PASS | REVIEW | FAIL |
|--------|------|--------|------|
| Required field extraction | ≥ 95% | 85–94% | < 85% |
| PDF downloads | 100% | — | < 95% |
| Travis CAD lookup success | ≥ 90% | 80–89% | < 80% |
| Tax Office lookup success | ≥ 85% | 75–84% | < 75% |
| Duplicate records | 0 | — | Any |

Results are written to `logs/run_YYYYMMDD.json` after every run.

---

## Error Handling

| Failure Type | Behaviour |
|--------------|-----------|
| Cloudflare challenge | Waits up to 2 minutes for real Chrome to auto-solve |
| PDF download failure | Retried 3× with exponential backoff; failure logged by instrument number |
| Already-downloaded PDF | Skipped instantly (idempotent runs) |
| CAD lookup failure | Retries with owner/grantor name; failure logged with address |
| Tax lookup failure | Retries with CAD account number; failure logged with address |
| Google Sheets API rate limit | tenacity retry with back-off |
| Missing PDF fields | Logged as null; record still written; counted in validation report |

---

## Project Structure

```
d:\Scrapper\
├── main.py                   # Async orchestrator — entry point
├── scheduler_setup.py        # Windows Task Scheduler registration
├── run_scraper.bat            # Batch wrapper called by Task Scheduler
├── requirements.txt           # Python dependencies
│
├── scraper/
│   ├── models.py              # Pydantic data models (ForeclosureRecord, etc.)
│   ├── config.py              # Config loader (YAML → dataclass)
│   ├── logger.py              # structlog setup with component binding
│   ├── clerk_scraper.py       # tccsearch.org — search, paginate, download PDFs
│   ├── pdf_extractor.py       # PDF → 14 structured fields (regex + OCR)
│   ├── cad_lookup.py          # Travis CAD cross-reference
│   ├── tax_lookup.py          # Tax Office cross-reference
│   ├── google_drive.py        # PDF upload → shareable Drive link
│   ├── google_sheets.py       # Sheet append with dedup
│   └── validator.py           # Field validation + PASS/REVIEW/FAIL report
│
├── config/
│   ├── config.yaml            # Runtime config (Sheet ID, Drive ID, timeouts)
│   └── credentials.json       # Google OAuth2 credentials (not in git)
│
├── tests/
│   └── test_pdf_extractor.py  # Unit tests for extraction logic
│
├── downloads/                 # Local PDF cache (date-organised)
└── logs/                      # JSON run reports
```

---

## Known Limitations

- **Cloudflare**: tccsearch.org uses Cloudflare bot protection. The scraper copies the real Chrome user profile to pass as a real browser session. If Cloudflare tightens its challenge (e.g., CAPTCHA), run with `headless: false` in `config/config.yaml`, solve once manually, and subsequent runs will use the saved session.
- **Task Scheduler admin**: Registering the scheduled task requires a one-time admin-elevated run of `scheduler_setup.py`. The task itself runs under SYSTEM with highest privileges after that.
- **OCR quality**: Scanned PDFs (minority of filings) use tesseract OCR at 300 DPI. Extraction accuracy is slightly lower on degraded scans but the system still extracts the critical fields (sale date, grantor, address) in all tested cases.

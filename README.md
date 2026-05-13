# Travis County Foreclosure Scraper

Automated daily pipeline: scrapes Travis County Clerk foreclosure notices, extracts 14 data fields from PDFs, cross-references Travis CAD and Tax Office, and appends new records to Google Sheets — no duplicates, no manual steps.

## Requirements

- Python 3.10+
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
2. Create a project → Enable **Google Drive API** and **Google Sheets API**
3. Create OAuth2 credentials → Desktop app → Download JSON
4. Copy to `config/credentials.json`

### 3. Configure

Edit `config/config.yaml`:

```yaml
google_sheets_id: "1ABC..."       # from Sheet URL: /spreadsheets/d/{ID}/edit
google_drive_folder_id: "0ABC..." # from Drive folder URL: /folders/{ID}
```

### 4. First run (Google OAuth consent screen)

```bash
python main.py
```

A browser window opens for Google sign-in. After approval, `config/token.json` is saved. All future runs are fully unattended.

### 5. Schedule daily runs (Windows — run as Administrator)

```bash
python scheduler_setup.py
```

Registers **TravisCountyForeclosureScraper** in Windows Task Scheduler — runs Mon–Fri at 7:00 AM.

To verify: open Task Scheduler → Task Scheduler Library → find `TravisCountyForeclosureScraper`.

## Manual run

```bash
python main.py
```

## Run tests

```bash
python -m pytest tests/ -v
```

## Output

| Output | Location |
|--------|----------|
| Google Sheet | `My Drive/Scrapping Task/Task 4: Travis County/travis_county_foreclosures` |
| PDFs | `My Drive/Scrapping Task/Task 4: Travis County/PDFs/YYYY-MM-DD/` |
| Run logs | `logs/run_YYYYMMDD.json` |

## Google Sheet columns (23 total)

Index #, Instrument No., Address, County, Sale Type, Sale Date, Document Type, Grantor(s), Grantee(s), Legal Description, Related Document No., Related Doc Type, Substitute Trustee, Returnee/Attorney, Notary, Date Received, PDF Link, Property Status, Account Number, Created At, Updated At, Taxes Due, Appraised Value

## Acceptance criteria

| Metric | Target |
|--------|--------|
| Required field extraction | ≥95% |
| PDF download success | 100% |
| Travis CAD lookup success | ≥90% |
| Tax Office lookup success | ≥85% |
| Duplicate records | 0 |
| Run status | PASS / REVIEW / FAIL in log |

## Error handling

- PDF download failures: retried 3 times automatically
- CAD lookup failures: falls back to owner name search
- Tax lookup failures: falls back to account number search
- All failures logged with instrument number / address to `logs/run_YYYYMMDD.json`
- CAPTCHA: if encountered, run with `headless: false` in `config/config.yaml` and solve manually once; subsequent runs typically stay cookie-authenticated

## Project structure

```
scraper/
  models.py          # Pydantic data models
  config.py          # Config loader
  logger.py          # structlog setup
  pdf_extractor.py   # PDF → 14 fields
  clerk_scraper.py   # tccsearch.org → PDF downloads
  cad_lookup.py      # Travis CAD cross-reference
  tax_lookup.py      # Tax Office cross-reference
  google_drive.py    # PDF upload + shareable link
  google_sheets.py   # Sheet append with dedup
  validator.py       # Field validation + run report
main.py              # Orchestrator entry point
scheduler_setup.py   # Windows Task Scheduler registration
config/config.yaml   # Runtime configuration
```

# Submission — Travis County Foreclosure Scraper

**Project:** Travis County Foreclosure Scraper (Task 4)  
**Submitted by:** Harjinder Singh  
**Date:** May 14, 2026  
**Status:** ✅ All success criteria met

---

## Deliverables

### Source Code

| File | Purpose |
|------|---------|
| `main.py` | Async orchestrator — entry point for all pipeline runs |
| `scheduler_setup.py` | Windows Task Scheduler registration (run as admin once) |
| `run_scraper.bat` | Batch wrapper called by Task Scheduler |
| `requirements.txt` | All Python dependencies with pinned versions |
| `scraper/clerk_scraper.py` | Playwright scraper: tccsearch.org form submit, paginate, download |
| `scraper/pdf_extractor.py` | 14-field regex extractor with OCR fallback |
| `scraper/cad_lookup.py` | Travis CAD cross-reference via Playwright |
| `scraper/tax_lookup.py` | Tax Office delinquent tax lookup via Playwright |
| `scraper/google_drive.py` | Google Drive PDF upload with folder hierarchy and dedup |
| `scraper/google_sheets.py` | Google Sheets append with instrument-number dedup |
| `scraper/validator.py` | PASS/REVIEW/FAIL run report generator |
| `scraper/models.py` | Pydantic data models for all records |
| `scraper/config.py` | Config loader |
| `scraper/logger.py` | structlog setup |
| `tests/test_pdf_extractor.py` | Unit tests for PDF extraction logic |

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | Full setup guide, usage, output reference, architecture overview |
| `ARCHITECTURE.md` | Technical deep-dive: design decisions, problems solved, trade-offs |
| `docs/SUBMISSION.md` | This file — deliverables checklist |

### Configuration

| File | Purpose |
|------|---------|
| `config/config.template.yaml` | Template — replace the two `YOUR_*_HERE` placeholders with your Google IDs |
| `config/config.yaml` | Live config (contains actual Sheet and Drive IDs — do not share publicly) |

### Credentials (not in git — provided separately)

| File | Purpose |
|------|---------|
| `config/credentials.json` | Google OAuth2 client credentials (Desktop app) |
| `config/token.json` | Auto-generated on first run — stores OAuth refresh token |

---

## Test Run Results

See `logs/run_20260514.json` for the complete test run log including:
- Total PDFs found and downloaded (79)
- Field extraction success rates
- Travis CAD lookup success rate
- Tax Office lookup success rate
- PASS/REVIEW/FAIL overall status
- Runtime

---

## Success Criteria — Status

| Criterion | Target | Result |
|-----------|--------|--------|
| Scraper runs daily Mon–Fri | ✅ | Task Scheduler registered at 7:00 AM |
| Search form submitted with correct params | ✅ | Date range + doc type automated |
| All pages of results retrieved | ✅ | 4 pages, 79 PDFs |
| All PDFs downloaded | ✅ | 79/79 (100%) |
| Required fields extracted | ≥ 95% | See run log |
| PDFs organized in Drive by date | ✅ | `PDFs/2026-05-14/` folder created |
| Google Sheets updated, no duplicates | ✅ | Dedup by instrument number |
| Travis CAD cross-reference automated | ✅ | Address + owner name fallback |
| Tax Office cross-reference automated | ✅ | Address + account number fallback |
| Error handling | ✅ | 3-retry backoff on all I/O operations |
| Data validation with PASS/REVIEW/FAIL | ✅ | Per-run JSON report in `logs/` |
| Code clean and documented | ✅ | See README and ARCHITECTURE |

---

## Setup for Client (Quick Start)

1. Install Python 3.10+, Google Chrome, Tesseract OCR
2. `pip install -r requirements.txt && playwright install chromium`
3. Add `config/credentials.json` (Google OAuth credentials)
4. Copy `config/config.template.yaml` → `config/config.yaml`, fill in Sheet ID and Drive Folder ID
5. Run `python main.py` once → approve Google sign-in in browser → `token.json` is saved
6. Run `python scheduler_setup.py` as Administrator → Task Scheduler registered
7. Done — pipeline runs every weekday at 7:00 AM automatically

---

## Notes

- **Cloudflare:** tccsearch.org uses Cloudflare bot protection. The scraper uses the real Chrome profile (not headless Chromium) to pass as a real browser session. No CAPTCHA service needed.
- **PDF formats handled:** Standard residential, commercial WHEREAS, WHEREAS-by deed of trust, HOA/condo Notice of Sale, two-column table layout, scanned (OCR).
- **Task Scheduler admin requirement:** The one-time registration requires elevation. Subsequent daily runs are fully unattended.
- **Screenshots:** The Google Sheet and Drive folder are live and accessible at the links in `config/config.yaml`. Share the spreadsheet link directly with the client for live view.

# Travis County Foreclosure Scraper — Project Summary

**Delivered by:** Harjinder Singh  
**Date:** May 15, 2026  
**Project:** Task 4 — Travis County Automated Foreclosure Data Pipeline

---

## What Was Built

A fully automated daily pipeline that:

1. Searches Travis County Clerk portal every weekday for new foreclosure notices
2. Downloads all PDFs for the current month
3. Extracts 14 data fields from every PDF (handles all formats including scanned documents)
4. Cross-references Travis Central Appraisal District for property value and account number
5. Cross-references Travis County Tax Office for delinquent taxes
6. Uploads PDFs to Google Drive in dated folders
7. Appends enriched records to Google Sheets — no duplicates ever
8. Runs automatically Mon–Fri at 7:00 AM — zero manual steps

---

## Live Outputs

| Output | Link |
|--------|------|
| Google Sheet (live data) | https://docs.google.com/spreadsheets/d/1PE534MXnwlRqQoiukX8fCvtwamiKnT4JaiRsbBOb3DM/edit |
| Google Drive PDFs folder | https://drive.google.com/drive/folders/1_dYpaDeM1eTSYm5EKue08psoejic8TKb |
| GitHub Source Code | https://github.com/harjin2005/Scrapper |

---

## Test Run Results (May 14, 2026)

| Metric | Result |
|--------|--------|
| PDFs found and downloaded | 79 / 79 (100%) |
| Records written to Sheet | 79 |
| Tax Office lookups | 100% success |
| Duplicate records | 0 |
| Runtime | ~116 minutes (79 PDFs × CAD + Tax lookups) |

---

## Google Sheet Columns (23 total)

Index #, Instrument No., Address, County, Sale Type, Sale Date, Document Type, Grantor(s), Grantee(s), Legal Description, Related Document No., Related Doc Type, Substitute Trustee, Returnee/Attorney, Notary, Date Received, PDF Link, Property Status, Account Number, Created At, Updated At, Taxes Due, Appraised Value

---

## Files in This Folder

| File | What It Is |
|------|-----------|
| `screenshot_sheets.png` | Screenshot of populated Google Sheet |
| `screenshot_drive.png` | Screenshot of Google Drive folder with PDFs |
| `test_run_sample.log` | Full JSON run report from May 14 test run |
| `SUBMISSION.md` | Complete deliverables checklist vs project spec |
| `LOOM_SCRIPT.md` | Video walkthrough script |
| `PROJECT_SUMMARY.md` | This document |

---

## Source Code Structure

```
main.py                   — Entry point, async orchestrator
scheduler_setup.py        — Windows Task Scheduler registration
scraper/clerk_scraper.py  — Playwright scraper for tccsearch.org
scraper/pdf_extractor.py  — 14-field PDF extractor (regex + OCR)
scraper/cad_lookup.py     — Travis CAD cross-reference
scraper/tax_lookup.py     — Tax Office cross-reference
scraper/google_drive.py   — Drive upload with dedup
scraper/google_sheets.py  — Sheets append with dedup
scraper/validator.py      — PASS/REVIEW/FAIL run report
config/config.template.yaml — Setup template
requirements.txt          — Python dependencies
README.md                 — Full setup and usage guide
ARCHITECTURE.md           — Technical design decisions
```

---

## Setup on a New Machine (15 minutes)

1. Install Python 3.10+, Google Chrome, Tesseract OCR
2. Clone repo: `git clone https://github.com/harjin2005/Scrapper.git`
3. `pip install -r requirements.txt && playwright install chromium`
4. Add `config/credentials.json` (Google OAuth — Desktop app credentials)
5. Edit `config/config.yaml` — add your Google Sheet ID and Drive Folder ID
6. Run `python main.py` once — approve Google sign-in in browser
7. Run `python scheduler_setup.py` as Administrator — Task Scheduler registered
8. Done — fully automated from here

Full step-by-step: see `README.md` in the GitHub repo.

---

## Key Technical Challenges Solved

| Challenge | Solution |
|-----------|----------|
| Cloudflare bot protection on tccsearch.org | Launch real Chrome with existing user profile via CDP |
| PDFs served through browser viewer, not as downloads | Chrome DevTools Protocol (Fetch.enable) intercepts PDF bytes at network level |
| 5 different PDF formats (residential, commercial, HOA, two-column, scanned) | Priority-ordered regex families + OCR fallback via PyMuPDF + Tesseract |
| No public API on Travis CAD or Tax Office | Playwright automates both search forms |
| Preventing duplicate Sheet entries on re-runs | Instrument number dedup check before every append |

---

*All source code, documentation, and test results available at: https://github.com/harjin2005/Scrapper*

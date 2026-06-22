# Travis County Foreclosure Lead System — Architecture

**Client:** Deed Geeks / Realty Simplified  
**Phase:** 1 — Travis County  
**Date:** June 2026  
**Status:** Architecture confirmed. Implementation in progress.

---

## System Overview

Fully automated daily pipeline that collects Travis County foreclosure filings, enriches each record across three authoritative data sources, validates completeness, and delivers research-ready leads to the team before 12:00 AM CST.

Zero manual steps between filing and the research team's queue.

---

## Pipeline Layers

### Layer 1 — Collection (Travis County Clerk)
**Source:** https://www.tccsearch.org  
**What it does:** Searches for all Notice of Substitute Trustee Sale filings from the first day of the current month through today, sorted by date filed descending. Paginates through all result pages. Downloads every PDF.

**Key detail:** The search results listing grid itself contains grantor name, sale date, and legal description. We capture these directly from the grid — before opening any PDF — and use them as a cross-reference baseline.

---

### Layer 2 — Extraction (PDF Parsing)
**Tool:** pdfplumber (Python)  
**What it does:** Extracts 14 structured fields from each downloaded PDF using regex patterns.

Fields extracted:
- Instrument Number, Property Address, Legal Description
- Sale Date, Grantor(s), Grantee(s)
- Original Loan Amount, Deed of Trust Recording Number
- Substitute Trustee, Attorney/Returnee
- Cause Number, Probate/Bankruptcy/Divorce Numbers

**Known constraint:** PDFs have no standard format. Address is sometimes missing. This is handled at Layer 3.

---

### Layer 3 — Cross-Reference (Listing vs PDF)
**What it does:** Compares the data captured from the search results grid (Layer 1) against the data extracted from the PDF (Layer 2) for three fields: grantor name, sale date, legal description.

**Rule:** County Clerk's filing system is authoritative over the PDF. On mismatch, the listing value wins and the discrepancy is logged.

---

### Layer 4 — Enrichment A: Travis CAD
**Source:** https://travis.prodigycad.com/property-search  
**Method:** Playwright browser automation with TrueProdigy API interception

**How it works (live-verified):**  
The CAD portal is a React application backed by the TrueProdigy API at `prod-container.trueprodigyapi.com`. When a search is performed, the browser intercepts the JSON response from `/public/property/searchfulltext`. This single API call returns every property field needed — no UI scraping required.

**Search strategy:**
1. Search by property address (primary)
2. If no address in PDF → search by owner name (fallback per business rule)
3. If multiple results → use legal description as tie-breaker (confirmed by Ralph)

**Critical field discovered:** `taxOfficeRef` in the API response is the Tax Assessor UID with leading zero (e.g. `01070028210000`). This is used directly in Layer 5 — no separate Tax Assessor search needed.

**Fields captured from one API call:**
- UID (via taxOfficeRef)
- Property Owner Name + Secondary Owner
- Property Street, City, State, Zip (separate fields)
- Mailing Street, City, State, Zip (separate fields)
- Appraised Value (2026 current year)
- Property Type Code + Property Type
- Acreage, AG Taxable Value
- Legal Description
- Date Bought By Current Owner

---

### Layer 5 — Enrichment B: Travis Tax Assessor
**Source:** https://tax-office.traviscountytx.gov (served by go2gov.net)  
**Method:** Direct URL construction — no search required

**How it works (live-verified):**  
The UID from Layer 4 (`taxOfficeRef`) maps directly to the Tax Assessor's account number. We construct the detail URL without searching:

```
https://travis.go2gov.net/showPropertyEntityDetail.do?account={UID}&year={current_year}
```

The detail page returns: Total Due, Legal Description, Account Number.  
The Receipts tab returns: Last Tax Payment Date.  
The Prior Bill tab returns: Initial Delinquency Year.

**Efficiency:** Because the UID comes from CAD, we skip the Tax Assessor search entirely — saving one browser session per record.

---

### Layer 6 — Enrichment C: MLS Verification
**Method:** Playwright on Bing search (live-verified — Google bot-detects headless browsers)

**How it works:**  
Bing search for `"{property address} zillow OR redfin OR realtor"`. If any of the three platforms appear in the results, the property is flagged as MLS Listed = Yes.

**Field produced:** `listed_on_mls` (Yes / No)

---

### Layer 7 — Validation and Deduplication
**Primary key:** UID (Tax Assessor account number, confirmed by Ralph)

**Dedup rule:** If UID already exists in Google Sheets → skip. Same owner appearing on multiple properties is NOT a duplicate — only UID determines uniqueness.

**Validation:** Each record is scored on field completion. Required fields: UID, Instrument Number, Grantor, Sale Date, PDF Link.

---

### Layer 8 — Review Layer (Google Sheets)
**Destination:** Google Sheets (linked to Google Drive)  
**Purpose:** Human review and data cleaning before Airtable promotion

Records land here first. Research team reviews before records are promoted to Airtable as Priority 0.

---

### Layer 9 — Airtable Priority 0 (Pending)
**Status:** Requirements gathering with Ralph. Not yet implemented.  
**Pending:** Required fields, minimum completeness threshold, priority assignment rules.

---

## Schedule

| Parameter | Value |
|---|---|
| Frequency | Daily |
| Deadline | Before 12:00 AM CST |
| Date range | First of current month → today |
| Sort order | File date descending |
| Days | Monday–Friday |

---

## Edge Case Handling

| Scenario | Handling |
|---|---|
| PDF has no property address | Search CAD by owner name (business rule confirmed) |
| Multiple CAD matches | Legal description as tie-breaker (confirmed by Ralph) |
| Same owner, multiple properties | Treat as separate records — UID is primary key |
| CAD lookup fails | Log miss, continue with available data |
| Tax Assessor lookup fails | Log miss, continue |
| PDF download fails | Retry 3 times with exponential backoff |
| Listing vs PDF mismatch | Log mismatch, listing value wins |
| UID already in sheet | Skip — already processed |

---

## Technology Stack

| Component | Technology |
|---|---|
| Browser automation | Python 3.11 + Playwright (async) |
| PDF extraction | pdfplumber |
| API interception | Playwright `page.on("response")` |
| Data models | Pydantic v2 |
| Google APIs | google-api-python-client |
| Logging | structlog |
| Retry logic | tenacity |
| Scheduling | Windows Task Scheduler / cron |

---

## What Has Been Live-Verified

| Claim | Status |
|---|---|
| Travis CAD uses TrueProdigy API — same as MCAD | Verified |
| One search call returns all 20+ CAD fields | Verified |
| taxOfficeRef = Tax Assessor UID | Verified |
| go2gov direct URL works without search | Verified |
| Bing search works for MLS check (Google bot-detects) | Verified |
| PDF listing grid contains grantor, sale date, legal desc | Verified |

---

## What Remains Pending

| Item | Owner | Blocker |
|---|---|---|
| go2gov RECEIPTS tab structure (last payment date) | Engineering | Investigation needed |
| go2gov PRIOR BILL tab structure (delinquency year) | Engineering | Investigation needed |
| CAD /deeds endpoint (purchase date) | Engineering | Investigation needed |
| Airtable field mapping + priority rules | Ralph | Business decision |
| Manual review criteria | Ralph | Business decision |
| Record rejection criteria | Ralph | Business decision |

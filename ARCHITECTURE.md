# Architecture & Design Decisions

Technical deep-dive on how the Travis County Foreclosure Scraper was built — the problems encountered, why each approach was chosen, and what was solved.

---

## 1. Cloudflare Bypass — Why Real Chrome

**Problem:** tccsearch.org (Travis County Clerk portal) is protected by Cloudflare. Standard headless browsers (Playwright Chromium, Puppeteer) are immediately detected and served a JavaScript challenge ("Just a moment…") that never resolves.

**Solution:** Launch the user's actual Google Chrome installation (not bundled Chromium) by copying the real Chrome profile (`AppData/Local/Google/Chrome/User Data/Default`) into a temporary directory and starting Chrome with `--remote-debugging-port`. Playwright connects over CDP (Chrome DevTools Protocol) to control it.

The real Chrome profile carries existing cookies, browser fingerprint, and TLS fingerprinting from years of regular use — Cloudflare accepts it as a legitimate browser session.

**Trade-off:** Requires Google Chrome installed at the default Windows path. Headless mode is disabled (Chrome runs minimised). Profile copy excludes cache folders to keep startup fast (~3 seconds).

---

## 2. PDF Download — Why CDP Fetch Interception

**Problem:** The clerk portal doesn't serve PDFs as direct file downloads. Clicking a document link opens a printHelper ASP.NET page that generates a server-side PDF and returns it as `Content-Type: application/pdf`. Chrome's built-in PDF viewer intercepts the response and wraps it in a PDF viewer extension page — making it impossible to capture the raw bytes via standard download events.

**Two-step solution:**

1. **Step 1:** Load `printHelper.aspx?t=P&id={global_id}&rnd={random}` in a temporary page. Parse the HTML response to extract a server-generated `r=` token (a session-scoped PDF render reference).

2. **Step 2:** Enable `Fetch.enable` via CDP before navigating to `printHelper.aspx?r={r_val}`. The CDP Fetch domain intercepts the PDF response *before* Chrome's PDF viewer sees it. Extract raw bytes from `Fetch.getResponseBody`, write to disk, then `continueRequest` so Chrome proceeds normally.

**Result:** PDF bytes are captured at the network layer, bypassing the PDF viewer entirely. No temporary files, no browser download directory needed.

---

## 3. PDF Extraction — Multi-Format, Multi-Strategy

**Problem:** Travis County foreclosure PDFs come in five structurally different formats:

| Format | Characteristics |
|--------|----------------|
| Standard residential | Inline prose, "with NAME, grantor" clause |
| Commercial WHEREAS | "WHEREAS, ENTITY NAME, a [State] [type]" |
| WHEREAS-by format | "WHEREAS, by a deed of trust… ENTITY to secure a debt to" |
| HOA/condo Notice of Sale | "indebtedness of NAME resulting from" |
| Two-column table | Labels in left column, values in right; pdfplumber extracts them as separate text blocks |

Some older filings are **scanned images** — pdfplumber returns empty text.

**Solution — layered extraction:**

```
pdfplumber.extract_text()
    │
    ├─ has text → regex pattern families (6 per field, priority-ordered)
    │
    └─ empty → OCR fallback:
               PyMuPDF renders each page at 300 DPI → PIL Image
               pytesseract → text string
               → same regex patterns
```

**Key regex engineering decisions:**

- **sale_date:** Priority 3 ("Tuesday, June 3, 2026") runs BEFORE Priority 3b ("on June 3, 2026") — otherwise recording dates ("recorded on May 15, 2018") match before sale dates.

- **OCR ordinal artifact:** tesseract renders "2nd" as `2"4` (superscript artifacts). Pattern allows `[^,A-Za-z\n]{0,6}` as junk between date digit and comma to absorb these artifacts.

- **Two-column separator:** tesseract renders bullet glyphs (•, ‣, ⁃) as U+FFFD (replacement character). Pattern uses `[^\w\s]` (any non-word, non-space) to match all single-symbol separators regardless of encoding.

- **Boilerplate filtering:** Post-extraction, values ending in `:` (another label) or matching known header words (Address, Trustee, Lender…) are rejected — prevents label text from being captured as a field value.

---

## 4. CAD Lookup — Why Playwright Instead of API

**Problem:** travis.prodigycad.com has no public API. The search form uses JavaScript-rendered results via Infragistics web controls — not accessible via plain HTTP requests.

**Solution:** Playwright automates the search form, waits for the results grid to render, and extracts account number, appraised value, and property status via page evaluation.

**Fallback chain:**
1. Search by property address
2. If no results → search by grantor name (owner name)

---

## 5. Tax Office Lookup — iframe Structure

**Problem:** The Travis County Tax Office search (`tax-office.traviscountytx.gov`) embeds the actual property tax data in a `go2gov.net` iframe with a separate domain and session cookie.

**Solution:** Navigate to the outer page, wait for the iframe to load, then switch Playwright's page context to the iframe's `contentFrame()`. Search by address or CAD account number. Parse the tax table from the iframe DOM.

---

## 6. Google Drive — Deduplication

Each run's PDFs are uploaded to `My Drive/Scrapping Task/Task 4: Travis County/PDFs/YYYY-MM-DD/`. Before uploading, the uploader checks whether a file with the same name already exists in the dated folder (via `files().list()` API call). If it does, the existing shareable link is returned — no duplicate upload, no double billing on Drive storage.

---

## 7. Google Sheets — Deduplication Strategy

The dedup key is the clerk portal **Instrument Number** — the document ID assigned by Travis County Clerk at filing time. It is unique per filing and stable (never changes).

On every append, the writer fetches all values in column B (Instrument No.), builds a set, and checks membership before inserting. This is O(n) on sheet size but acceptable for the expected scale (a few hundred rows per month).

---

## 8. Instrument Number Source

Travis County Clerk foreclosure PDFs contain multiple document numbers:
- The **foreclosure notice filing number** (from the clerk portal search results, e.g., `202640690`) — this is the unique ID for the Notice of Substitute Trustee Sale
- The **deed of trust instrument number** (in the PDF body text, e.g., `2023071621`) — this is the original mortgage filing being foreclosed on

The correct identifier for dedup and cross-referencing is the **clerk portal filing number**. The pipeline uses the filename (which is always `{clerk_instrument_no}_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf`) as the authoritative source for instrument number, not the PDF body text.

The deed of trust number goes into **Related Document No.** (column 11) via the extractor's `_extract_related_doc_no` method.

---

## 9. Scheduling — Windows Task Scheduler

The daily automation uses Windows Task Scheduler with:
- **Account:** SYSTEM (S-1-5-18) — runs whether or not the user is logged in
- **Run level:** Highest — bypasses UAC for Chrome profile operations
- **Trigger:** Weekly, Mon–Fri at 07:00
- **Action:** `D:\Scrapper\run_scraper.bat` (sets working directory, activates venv if needed, runs `python main.py`)

Registration requires a one-time admin-elevated run of `python scheduler_setup.py`. After that, the task runs fully unattended.

---

## 10. Retry & Error Resilience

| Layer | Retry mechanism |
|-------|----------------|
| PDF download | tenacity: 3 attempts, exponential backoff 2–10s |
| Google Drive upload | tenacity on the underlying `googleapiclient` transport |
| Google Sheets append | tenacity |
| CAD / Tax Playwright | Outer try/except per record; failure logged, pipeline continues |

The pipeline never aborts on a single record failure. All failures are collected into the run report (`logs/run_YYYYMMDD.json`) with instrument number, address, and error string.

---

## 11. Structured Logging

Every component uses `structlog` with component binding:

```python
log = get_logger("clerk_scraper")
log.info("pdf_downloaded", instrument_no=instrument_no, global_id=global_id)
```

Output: `2026-05-14 21:58:21 [info] pdf_downloaded component=clerk_scraper instrument_no=202640690 global_id=OPR1117348090`

All log lines are machine-parseable. The JSON run report at `logs/run_YYYYMMDD.json` captures aggregated metrics (extraction rates, CAD/tax success rates, total runtime, PASS/REVIEW/FAIL status).

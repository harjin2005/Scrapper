# Montgomery County Delinquent Tax Roll Processor

Automated weekly pipeline that downloads the Montgomery County Delinquent Tax Roll Excel file, cross-references each account against MCAD and the Tax Office portal, then upserts all records into Google Sheets and uploads the source Excel to Google Drive.

---

## Architecture

```
mctotx.org
  ↓  check for new file (by "as of" date)
  ↓  download XLSX

excel_processor.py
  ↓  pandas load → DelinquentRecord list

For each record:
  mcad_lookup.py   → mcad-tx.org (AG Grid)  → property type, appraised value, lot size, legal desc
  tax_lookup.py    → actweb.acttax.com (JSP) → delinquency year, years behind, cause #, total due

sheets_writer.py   → Google Sheets upsert (UPDATE if acct exists, INSERT if new)
drive_uploader.py  → Google Drive upload (dated subfolder, dedup)

checkpoint.py      → JSON checkpoint — resume on crash
validator.py       → PASS / REVIEW / FAIL run report
```

---

## Prerequisites

| Requirement | Detail |
|---|---|
| Python 3.10+ | `python --version` |
| pandas + openpyxl | `pip install pandas openpyxl` |
| Playwright | `pip install playwright && playwright install chromium` |
| Google credentials | `config/credentials.json` (OAuth2 Desktop App) |
| VPN | US/Texas server required — mctotx.org and actweb.acttax.com block non-US IPs |

---

## Setup

### 1. Install dependencies

```bash
cd D:\Scrapper
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Google credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Sheets API** and **Google Drive API**
3. Create **OAuth2 Desktop App** credentials → download `credentials.json`
4. Place at `D:\Scrapper\config\credentials.json`

### 3. Edit config

Open `montgomery/config/config.yaml` and fill in:

```yaml
google_sheets_id: "YOUR_GOOGLE_SHEETS_ID_HERE"     # from Sheet URL
google_drive_folder_id: "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE"  # from Drive folder URL
```

### 4. First run (authorises Google OAuth)

```bash
cd D:\Scrapper
python -m montgomery.main
```

A browser window will open to authorise Google access. After that, `config/token.json` is created and subsequent runs are fully automated.

---

## Manual run

```bash
cd D:\Scrapper
python -m montgomery.main
```

The pipeline will:
1. Check mctotx.org for a new Delinquent Tax Roll (compares "as of" date to last run)
2. Download the XLSX if new
3. Upload XLSX to Google Drive
4. Parse all rows with pandas
5. For each account: query MCAD + Tax Office via Playwright
6. Upsert each record into Google Sheets
7. Save a JSON run report to `montgomery/logs/`

---

## Schedule (weekly — Monday 06:00 AM)

**Run once as Administrator:**

```bash
python D:\Scrapper\montgomery\scheduler_setup.py
```

Registers Windows Task Scheduler task `MontgomeryDelinquentTaxProcessor`.

Verify:
```bash
schtasks /Query /TN "MontgomeryDelinquentTaxProcessor" /FO LIST /V
```

Test immediately:
```bash
schtasks /Run /TN "MontgomeryDelinquentTaxProcessor"
```

---

## Google Sheet columns

| # | Column | Source |
|---|---|---|
| 1 | Account Number | Excel |
| 2 | Property Owner | Excel |
| 3 | Property Address | Excel |
| 4 | Mailing Address | MCAD |
| 5 | Property Type | MCAD |
| 6 | Property Type Code | MCAD |
| 7 | Lot Size | MCAD |
| 8 | Legal Description | Excel / MCAD |
| 9 | Owner Contact Number | MCAD |
| 10 | Email | MCAD |
| 11 | Last Tax Payment Date | Tax Office |
| 12 | Initial Delinquency Year | Tax Office |
| 13 | Years Behind Taxes | Tax Office |
| 14 | Cause / Lawsuit No | Tax Office |
| 15 | Cause Date | Tax Office |
| 16 | Appraised Value | MCAD |
| 17 | Total Tax Due | Tax Office / Excel |
| 18 | County | Static: "Montgomery" |
| 19 | Excel File Date | Excel download date |
| 20 | Created At | Pipeline timestamp |
| 21 | Updated At | Pipeline timestamp |

---

## Run report

After each run, `montgomery/logs/run_report_YYYY-MM-DD.json` contains:

```json
{
  "run_date": "2026-05-19",
  "excel_file_date": "May 11, 2026",
  "total_rows_in_excel": 1250,
  "rows_processed": 1248,
  "rows_added": 42,
  "rows_updated": 1206,
  "required_field_extraction_rate": 0.9984,
  "mcad_lookup_success_rate": 0.9712,
  "tax_lookup_success_rate": 0.9456,
  "overall_status": "PASS"
}
```

| Status | Meaning |
|---|---|
| PASS | All thresholds met |
| REVIEW | One metric below threshold — manual check recommended |
| FAIL | Required field rate < 85% or < 95% of rows processed |

---

## Checkpoint / resume

If the pipeline crashes mid-run, restart it. It reads `montgomery/checkpoints/checkpoint_*.json` and skips already-processed accounts automatically.

To force a full re-process, delete the checkpoint file:
```bash
del montgomery\checkpoints\checkpoint_*.json
```

---

## VPN requirement

Montgomery County Tax Office (`actweb.acttax.com`) and the MCAD portal (`mcad-tx.org`) block connections from non-US IP addresses. Connect to a US or Texas VPN server before running.

Recommended: ProtonVPN (free tier) → United States server.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `403 Forbidden` on mctotx.org | No VPN / non-US IP | Connect VPN to US server |
| `ECONNREFUSED` on actweb | Same as above | Same fix |
| `FileNotFoundError: credentials.json` | Missing OAuth file | Follow Setup step 2 |
| Sheet ID not found | Placeholder not replaced | Edit config.yaml |
| `ag-row not found` | MCAD page layout changed | Check mcad-tx.org manually; update selectors |
| Excel column not mapped | New column name in XLSX | Add to `_COL_MAP` in excel_processor.py |

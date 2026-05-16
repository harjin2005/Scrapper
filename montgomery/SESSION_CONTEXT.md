# Montgomery County — Session Context (Compaction Survival)

## What this is
Montgomery County Delinquent Tax Roll Processor — Task 5 in d:/Scrapper/montgomery/

## Architecture
Excel download → pandas processing → MCAD lookup (Playwright) → Tax Office lookup (Playwright) → Google Sheets upsert + Drive backup

## Sites
- Excel source: https://www.mctotx.org/property/property_tax_forms.php
- MCAD: https://mcad-tx.org/
- Tax Office: https://actweb.acttax.com/act_webdev/montgomery/index.jsp

## Key differences from Travis County (d:/Scrapper/scraper/)
- Excel not PDF — pandas column mapping not regex
- UPSERT not append — UPDATE row if account number exists
- Checkpointing every 100 records — resume on crash
- Weekly schedule not daily
- Potentially 10k+ rows — rate limiting required
- VPN needed for mctotx.org and actweb.acttax.com (403/blocked from non-US IPs)

## Modules
- config.py — config dataclass + YAML loader
- models.py — pydantic DelinquentRecord + RunReport
- excel_downloader.py — detect new file by "as of" date, download XLSX
- excel_processor.py — pandas load, clean, column mapping
- mcad_lookup.py — Playwright mcad-tx.org
- tax_lookup.py — Playwright actweb.acttax.com (JSP)
- sheets_writer.py — upsert by account number
- drive_uploader.py — upload Excel to Drive dated folder
- checkpoint.py — JSON checkpoint, resume from last processed row
- validator.py — PASS/REVIEW/FAIL thresholds
- main.py — async orchestrator
- scheduler_setup.py — Windows Task Scheduler weekly Monday 7am

## Google credentials
Shared with Travis County — d:/Scrapper/config/credentials.json + token.json

## Current build status
[ ] models.py
[ ] config.py + config.template.yaml
[ ] checkpoint.py
[ ] excel_downloader.py
[ ] excel_processor.py
[ ] mcad_lookup.py
[ ] tax_lookup.py
[ ] drive_uploader.py
[ ] sheets_writer.py
[ ] validator.py
[ ] main.py
[ ] scheduler_setup.py
[ ] README.md

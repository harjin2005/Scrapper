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

    pdf_pairs: list[tuple[str, str]] = []
    failed_downloads: list[str] = []
    try:
        pdf_pairs = await clerk.run(run_date)
    except Exception as exc:
        log.error("clerk_scraper_error", error=str(exc))

    log.info("pdfs_collected", count=len(pdf_pairs))

    records: list[ForeclosureRecord] = []
    cad_successes = 0
    tax_successes = 0
    failed_cad: list[str] = []
    failed_tax: list[str] = []

    for instrument_no, local_path in pdf_pairs:
        try:
            drive_link = drive.upload(local_path, run_date)
            record = extractor.extract(local_path, pdf_link=drive_link)

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

            try:
                tax_data = await tax.lookup(record.address, record.account_number)
                record.taxes_due = tax_data.taxes_due
                tax_successes += 1
            except Exception as tax_exc:
                log.error("tax_step_failed", instrument_no=instrument_no, error=str(tax_exc))
                failed_tax.append(record.address)

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

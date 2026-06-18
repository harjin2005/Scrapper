from __future__ import annotations
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Optional

from scraper.cad_lookup import CADLookup
from scraper.clerk_scraper import ClerkScraper
from scraper.config import load_config, Config
from scraper.google_drive import GoogleDriveUploader
from scraper.google_sheets import GoogleSheetsWriter
from scraper.logger import get_logger, setup_logging
from scraper.mls_lookup import MlsLookup
from scraper.models import ForeclosureRecord, ListingEntry
from scraper.pdf_extractor import PDFExtractor
from scraper.tax_lookup import TaxLookup
from scraper.validator import Validator


def _normalize(s: str | None) -> str:
    return " ".join((s or "").upper().split())


def _cross_reference(record: ForeclosureRecord, entry: ListingEntry, log) -> None:
    """Compare clerk listing grid data vs PDF extraction. Listing is authoritative on conflict."""
    mismatches: list[str] = []

    if entry.grantor_listing:
        pdf_g = _normalize(record.grantor)
        listing_g = _normalize(entry.grantor_listing)
        if pdf_g and listing_g and pdf_g != listing_g:
            mismatches.append(f"grantor: pdf='{record.grantor}' listing='{entry.grantor_listing}'")
            record.grantor = entry.grantor_listing

    if entry.sale_date_listing:
        from datetime import datetime
        try:
            listing_sale = datetime.strptime(entry.sale_date_listing, "%m/%d/%Y").date()
            if record.sale_date and record.sale_date != listing_sale:
                mismatches.append(
                    f"sale_date: pdf='{record.sale_date}' listing='{listing_sale}'"
                )
            record.sale_date = listing_sale
        except ValueError:
            pass

    if entry.legal_desc_listing:
        pdf_ld = _normalize(record.legal_description)
        listing_ld = _normalize(entry.legal_desc_listing)
        if pdf_ld and listing_ld and pdf_ld != listing_ld:
            mismatches.append(
                f"legal_desc: pdf='{record.legal_description}' listing='{entry.legal_desc_listing}'"
            )
            record.legal_description = entry.legal_desc_listing

    if mismatches:
        log.warning("cross_ref_mismatch", instrument_no=record.instrument_no, mismatches=mismatches)
    else:
        log.info("cross_ref_ok", instrument_no=record.instrument_no)


async def run_pipeline(config: Config, run_date: Optional[date] = None) -> object:
    run_date = run_date or date.today()
    log = get_logger("orchestrator")
    setup_logging(config.logs_dir)
    start = time.monotonic()

    log.info("pipeline_start", run_date=str(run_date))

    clerk     = ClerkScraper(config)
    extractor = PDFExtractor()
    cad       = CADLookup(config)
    tax       = TaxLookup(config)
    mls       = MlsLookup(config)
    drive     = GoogleDriveUploader(config)
    sheets    = GoogleSheetsWriter(config)
    validator = Validator()

    sheets.ensure_headers()
    existing_uids: set[str] = sheets.get_existing_uids()

    listing_entries: list[ListingEntry] = []
    failed_downloads: list[str] = []
    try:
        listing_entries = await clerk.run(run_date)
    except Exception as exc:
        log.error("clerk_scraper_error", error=str(exc))

    log.info("pdfs_collected", count=len(listing_entries))

    records: list[ForeclosureRecord] = []
    cad_successes = 0
    tax_successes = 0
    failed_cad: list[str] = []
    failed_tax: list[str] = []

    for entry in listing_entries:
        instrument_no = entry.instrument_no
        local_path = entry.local_path
        try:
            drive_link = drive.upload(local_path, run_date)
            record = extractor.extract(local_path, pdf_link=drive_link)
            record.instrument_no = instrument_no

            _cross_reference(record, entry, log)

            # CAD enrichment
            try:
                cad_data = await cad.lookup(record.address, record.grantor)
                # Backward-compat fields
                record.account_number = cad_data.uid_raw
                record.appraised_value = cad_data.appraised_value
                record.property_status = cad_data.property_status
                # New CAD fields
                record.uid = cad_data.uid
                record.owner_name_cad = cad_data.owner_name
                record.owner_secondary = cad_data.owner_secondary
                record.property_street = cad_data.property_street
                record.property_city = cad_data.property_city
                record.property_state = cad_data.property_state
                record.property_zip = cad_data.property_zip
                record.mailing_street = cad_data.mailing_street
                record.mailing_city = cad_data.mailing_city
                record.mailing_state = cad_data.mailing_state
                record.mailing_zip = cad_data.mailing_zip
                record.property_type_code = cad_data.property_type_code
                record.acreage = cad_data.acreage
                record.legal_description_cad = cad_data.legal_description
                record.date_bought_by_owner = cad_data.date_bought_by_owner
                if cad_data.uid:
                    cad_successes += 1
                else:
                    failed_cad.append(record.address)
            except Exception as cad_exc:
                log.error("cad_step_failed", instrument_no=instrument_no, error=str(cad_exc))
                failed_cad.append(record.address)

            # Tax enrichment — pass uid_raw so tax uses direct URL
            try:
                tax_data = await tax.lookup(record.address, record.account_number)
                record.taxes_due = tax_data.taxes_due
                record.years_delinquent = tax_data.years_delinquent
                record.last_payment_date = tax_data.last_payment_date
                record.initial_delinquency_year = tax_data.initial_delinquency_year
                tax_successes += 1
            except Exception as tax_exc:
                log.error("tax_step_failed", instrument_no=instrument_no, error=str(tax_exc))
                failed_tax.append(record.address)

            # MLS check
            try:
                mls_address = record.property_street or record.address
                record.listed_on_mls = await mls.check(mls_address)
            except Exception as mls_exc:
                log.error("mls_step_failed", instrument_no=instrument_no, error=str(mls_exc))
                record.listed_on_mls = "No"

            # Dedup by UID (cross-run dedup)
            if record.uid and record.uid in existing_uids:
                log.info("dedup_skip", uid=record.uid, instrument_no=instrument_no)
                continue
            if record.uid:
                existing_uids.add(record.uid)

            sheets.append_record(record)
            records.append(record)

            # TODO: AirTable integration (Priority 0 upload)
            # Criteria TBD with client
            # airtable_writer.upload(record, priority=0)

        except Exception as exc:
            log.error("record_processing_failed", instrument_no=instrument_no, error=str(exc))
            failed_downloads.append(instrument_no)

    runtime = time.monotonic() - start
    from_date = date(run_date.year, run_date.month, 1).strftime("%m/%d/%Y")
    to_date = run_date.strftime("%m/%d/%Y")

    report = validator.build_run_report(
        run_date=str(run_date),
        date_range=f"{from_date} to {to_date}",
        total_found=len(listing_entries),
        downloaded=len(listing_entries) - len(failed_downloads),
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

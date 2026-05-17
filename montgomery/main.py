from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime, date
from pathlib import Path

from montgomery.config import load_config
from montgomery.checkpoint import Checkpoint
from montgomery.excel_downloader import check_for_new_file, download_excel, save_last_processed_date
from montgomery.excel_processor import load_excel
from montgomery.mcad_lookup import MCADLookup
from montgomery.tax_lookup import TaxLookup
from montgomery.sheets_writer import SheetsWriter
from montgomery.drive_uploader import DriveUploader
from montgomery.validator import build_report
from scraper.logger import get_logger

log = get_logger("montgomery.main")


async def run(
    config_path: str = "montgomery/config/config.yaml",
    local_xlsx: str | None = None,
) -> None:
    cfg = load_config(config_path)
    run_date = date.today()
    run_date_str = run_date.strftime("%Y-%m-%d")
    t_start = time.time()

    log.info("montgomery_run_start", run_date=run_date_str)

    # ── 1. Get Excel file — auto-download OR manual path ─────────────────────
    if local_xlsx:
        # Manual mode: user supplies local Excel path, skip website check
        xlsx_path = local_xlsx
        as_of_date = run_date_str
        log.info("manual_file_mode", path=xlsx_path)
    else:
        result = await check_for_new_file(cfg.tax_forms_url, cfg.downloads_dir)
        if result is None:
            log.info("no_new_file_skipping_run")
            return
        download_url, as_of_date = result

        # ── 2. Download Excel ────────────────────────────────────────────────
        xlsx_path = download_excel(download_url, as_of_date, cfg.downloads_dir)

    # ── 3. Upload Excel to Drive ─────────────────────────────────────────────
    drive = DriveUploader(
        folder_id=cfg.google_drive_folder_id,
        credentials_path=cfg.google_credentials_path,
        token_path=cfg.google_token_path,
    )
    drive_link = drive.upload(xlsx_path, run_date)
    log.info("excel_on_drive", link=drive_link)

    # ── 4. Parse Excel rows ──────────────────────────────────────────────────
    records = load_excel(xlsx_path, excel_file_date=as_of_date)
    total_rows = len(records)
    log.info("records_parsed", count=total_rows)

    if not records:
        log.error("no_records_parsed", xlsx_path=xlsx_path)
        return

    # ── 5. Init cross-ref clients and checkpoint ─────────────────────────────
    mcad = MCADLookup(cfg)
    tax = TaxLookup(cfg)
    sheets = SheetsWriter(
        spreadsheet_id=cfg.google_sheets_id,
        credentials_path=cfg.google_credentials_path,
        token_path=cfg.google_token_path,
    )
    checkpoint = Checkpoint(cfg.checkpoint_dir, as_of_date)

    processed_records: list = []
    failed_accounts: list[str] = []
    failed_mcad: list[str] = []
    failed_tax: list[str] = []
    added = 0
    updated = 0

    # ── 6. Process each record ───────────────────────────────────────────────
    for i, rec in enumerate(records, start=1):
        acct = rec.account_number

        if checkpoint.is_done(acct):
            log.info("skipping_already_processed", account=acct)
            continue

        log.info("processing_record", account=acct, progress=f"{i}/{total_rows}")

        # MCAD cross-reference — use appraisal district account (no leading zeros)
        mcad_acct = getattr(rec, "_aprdistacc", None) or acct
        try:
            cad_data = await mcad.lookup(mcad_acct)
            rec.property_type = cad_data.property_type
            rec.property_type_code = cad_data.property_type_code
            rec.appraised_value = cad_data.appraised_value
            rec.lot_size = cad_data.lot_size
            rec.legal_description = rec.legal_description or cad_data.legal_description
            rec.property_mailing_address = rec.property_mailing_address or cad_data.mailing_address
        except Exception as exc:
            log.error("mcad_lookup_error", account=acct, error=str(exc))
            failed_mcad.append(acct)

        # Tax Office cross-reference
        try:
            tax_data = await tax.lookup(acct)
            rec.last_tax_payment_date = tax_data.last_payment_date
            rec.initial_delinquency_year = tax_data.initial_delinquency_year
            rec.years_behind_taxes = tax_data.years_behind
            rec.cause_or_lawsuit_no = tax_data.cause_number
            rec.cause_date = tax_data.cause_date
            if not rec.total_tax_due:
                rec.total_tax_due = tax_data.total_due
        except Exception as exc:
            log.error("tax_lookup_error", account=acct, error=str(exc))
            failed_tax.append(acct)

        # Timestamps
        now_str = datetime.utcnow().isoformat()
        if not rec.created_at:
            rec.created_at = datetime.utcnow()
        rec.updated_at = datetime.utcnow()

        # Write to Sheets — only checkpoint on success
        try:
            action = sheets.upsert(rec)
            if action == "added":
                added += 1
            else:
                updated += 1
            processed_records.append(rec)
            checkpoint.mark_done(acct)
        except Exception as exc:
            log.error("sheets_upsert_error", account=acct, error=str(exc))
            failed_accounts.append(acct)

        # Save checkpoint every N records
        if i % cfg.checkpoint_every_n == 0:
            checkpoint.save()
            log.info("checkpoint_saved", at_record=i)

        # Rate limit
        await asyncio.sleep(cfg.rate_limit_delay_seconds)

    # Final checkpoint save
    checkpoint.save()

    # ── 7. Mark file as processed ────────────────────────────────────────────
    save_last_processed_date(cfg.downloads_dir, as_of_date)

    # ── 8. Build and save run report ─────────────────────────────────────────
    runtime = time.time() - t_start
    report = build_report(
        run_date=run_date_str,
        excel_file_date=as_of_date,
        total_rows_in_excel=total_rows,
        records=processed_records,
        added=added,
        updated=updated,
        failed_accounts=failed_accounts,
        failed_mcad=failed_mcad,
        failed_tax=failed_tax,
        runtime_seconds=runtime,
    )

    logs_dir = Path(cfg.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_path = logs_dir / f"run_report_{run_date_str}.json"
    report_path.write_text(json.dumps(report.model_dump(), indent=2))

    log.info(
        "montgomery_run_complete",
        status=report.overall_status,
        added=added,
        updated=updated,
        failed=len(failed_accounts),
        runtime_seconds=round(runtime, 1),
        report_path=str(report_path),
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Montgomery County Delinquent Tax Processor")
    parser.add_argument("--file", help="Path to local Excel file (skips website download)")
    parser.add_argument("--config", default="montgomery/config/config.yaml")
    args = parser.parse_args()
    asyncio.run(run(config_path=args.config, local_xlsx=args.file))


if __name__ == "__main__":
    main()

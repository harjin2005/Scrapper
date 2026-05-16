from __future__ import annotations
from montgomery.models import DelinquentRecord, RunReport
from scraper.logger import get_logger

log = get_logger("validator")


def build_report(
    run_date: str,
    excel_file_date: str,
    total_rows_in_excel: int,
    records: list[DelinquentRecord],
    added: int,
    updated: int,
    failed_accounts: list[str],
    failed_mcad: list[str],
    failed_tax: list[str],
    runtime_seconds: float,
) -> RunReport:
    processed = len(records)

    # Required fields: account_number + property_owner + property_address
    required_ok = sum(
        1
        for r in records
        if r.account_number and r.property_owner and r.property_address
    )
    required_rate = required_ok / processed if processed else 0.0

    # MCAD success = appraised_value populated
    mcad_ok = sum(1 for r in records if r.appraised_value)
    mcad_rate = mcad_ok / processed if processed else 0.0

    # Tax success = total_tax_due populated
    tax_ok = sum(1 for r in records if r.total_tax_due)
    tax_rate = tax_ok / processed if processed else 0.0

    report = RunReport(
        run_date=run_date,
        excel_file_date=excel_file_date,
        total_rows_in_excel=total_rows_in_excel,
        rows_processed=processed,
        rows_added=added,
        rows_updated=updated,
        required_field_extraction_rate=round(required_rate, 4),
        mcad_lookup_success_rate=round(mcad_rate, 4),
        tax_lookup_success_rate=round(tax_rate, 4),
        failed_account_numbers=failed_accounts,
        failed_mcad=failed_mcad,
        failed_tax=failed_tax,
        total_runtime_seconds=round(runtime_seconds, 2),
    )

    log.info(
        "run_report",
        status=report.overall_status,
        processed=processed,
        added=added,
        updated=updated,
        required_rate=f"{required_rate:.1%}",
        mcad_rate=f"{mcad_rate:.1%}",
        tax_rate=f"{tax_rate:.1%}",
    )
    return report

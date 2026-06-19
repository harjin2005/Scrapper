from __future__ import annotations
import re
from scraper.models import ForeclosureRecord, RunReport
from scraper.logger import get_logger
from scraper.pdf_extractor import _is_valid_name_field

log = get_logger("validator")

REQUIRED_FIELDS = ["instrument_no", "address", "grantor", "sale_date", "pdf_link"]


class Validator:
    def validate_record(self, record: ForeclosureRecord) -> tuple[bool, str]:
        """Pre-write validation — rejects records with missing/garbage required fields."""
        if not record.instrument_no:
            return False, "instrument_no empty"
        if not record.address or not re.search(r"\d", record.address):
            return False, "address missing or no street number"
        if record.sale_date is None:
            return False, "sale_date missing"
        if not record.grantor or not _is_valid_name_field(record.grantor):
            return False, "grantor missing or sentence fragment"
        return True, ""

    def validate_required_fields(self, record: ForeclosureRecord) -> tuple[bool, list[str]]:
        missing = []
        for field in REQUIRED_FIELDS:
            val = getattr(record, field, None)
            if not val:
                missing.append(field)
        return len(missing) == 0, missing

    def calculate_extraction_rate(self, records: list[ForeclosureRecord]) -> float:
        if not records:
            return 0.0
        passed = sum(1 for r in records if self.validate_required_fields(r)[0])
        return passed / len(records)

    def build_run_report(
        self,
        run_date: str,
        date_range: str,
        total_found: int,
        downloaded: int,
        records: list[ForeclosureRecord],
        cad_successes: int,
        tax_successes: int,
        failed_downloads: list[str],
        failed_cad: list[str],
        failed_tax: list[str],
        runtime_seconds: float,
        validation_failures: int = 0,
    ) -> RunReport:
        extraction_rate = self.calculate_extraction_rate(records)
        cad_rate = cad_successes / max(downloaded, 1)
        tax_rate = tax_successes / max(downloaded, 1)

        report = RunReport(
            run_date=run_date,
            date_range_searched=date_range,
            total_results=total_found,
            pdfs_downloaded=downloaded,
            records_processed=len(records),
            validation_failures=validation_failures,
            required_field_extraction_rate=extraction_rate,
            cad_lookup_success_rate=cad_rate,
            tax_lookup_success_rate=tax_rate,
            failed_downloads=failed_downloads,
            failed_cad_lookups=failed_cad,
            failed_tax_lookups=failed_tax,
            total_runtime_seconds=runtime_seconds,
        )
        log.info(
            "run_report_built",
            status=report.overall_status,
            extraction_rate=extraction_rate,
            cad_rate=cad_rate,
            tax_rate=tax_rate,
        )
        return report

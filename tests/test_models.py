import pytest
from datetime import date
from scraper.models import ForeclosureRecord, CADData, TaxData, RunReport


def test_foreclosure_record_required_fields():
    record = ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Main St, Austin TX 78701",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )
    assert record.instrument_no == "2026012345"
    assert record.county == "Travis"
    assert record.sale_type == "Substitute Trustee Sale"
    assert record.document_type == "Notice of Substitute Trustee Sale"


def test_foreclosure_record_defaults():
    record = ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Main St",
        grantor="Jane Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )
    assert record.taxes_due == "0"
    assert record.property_status is None
    assert record.account_number is None
    assert record.appraised_value is None


def test_cad_data_model():
    cad = CADData(
        uid="1070028210000",
        uid_raw="01070028210000",
        appraised_value="450000",
        property_status="Yes",
    )
    assert cad.uid == "1070028210000"
    assert cad.uid_raw == "01070028210000"
    assert cad.appraised_value == "450000"


def test_tax_data_model():
    tax = TaxData(taxes_due="12500.00", years_delinquent=3)
    assert tax.taxes_due == "12500.00"


def test_run_report_pass_criteria():
    report = RunReport(
        run_date="2026-05-13",
        date_range_searched="05/01/2026 to 05/13/2026",
        total_results=10,
        pdfs_downloaded=10,
        records_processed=10,
        required_field_extraction_rate=0.98,
        cad_lookup_success_rate=0.95,
        tax_lookup_success_rate=0.90,
        failed_downloads=[],
        failed_cad_lookups=[],
        failed_tax_lookups=[],
        total_runtime_seconds=120.5,
    )
    assert report.overall_status == "PASS"


def test_run_report_fail_criteria():
    report = RunReport(
        run_date="2026-05-13",
        date_range_searched="05/01/2026 to 05/13/2026",
        total_results=10,
        pdfs_downloaded=9,
        records_processed=9,
        required_field_extraction_rate=0.80,
        cad_lookup_success_rate=0.70,
        tax_lookup_success_rate=0.60,
        failed_downloads=["2026099999"],
        failed_cad_lookups=["123 Main St"],
        failed_tax_lookups=["123 Main St"],
        total_runtime_seconds=95.0,
    )
    assert report.overall_status == "FAIL"

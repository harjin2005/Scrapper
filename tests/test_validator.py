import pytest
from datetime import date
from scraper.validator import Validator
from scraper.models import ForeclosureRecord


@pytest.fixture
def complete_record():
    return ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Oak St, Austin TX 78701",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )


@pytest.fixture
def incomplete_record():
    return ForeclosureRecord(
        instrument_no="2026099999",
        address="",
        grantor="",
        sale_date=None,
        pdf_link="https://drive.google.com/file/def",
    )


def test_validate_complete_record(complete_record):
    v = Validator()
    passed, missing = v.validate_required_fields(complete_record)
    assert passed is True
    assert len(missing) == 0


def test_validate_incomplete_record(incomplete_record):
    v = Validator()
    passed, missing = v.validate_required_fields(incomplete_record)
    assert passed is False
    assert "address" in missing or "grantor" in missing


def test_extraction_rate_calculation():
    v = Validator()
    records = [
        ForeclosureRecord(
            instrument_no="001", address="123 A St", grantor="Doe",
            sale_date=date(2026, 6, 3), pdf_link="https://x"
        ),
        ForeclosureRecord(
            instrument_no="002", address="", grantor="",
            sale_date=None, pdf_link="https://y"
        ),
    ]
    rate = v.calculate_extraction_rate(records)
    assert rate == 0.5


def test_full_run_report_generation():
    v = Validator()
    report = v.build_run_report(
        run_date="2026-05-13",
        date_range="05/01/2026 to 05/13/2026",
        total_found=10,
        downloaded=10,
        records=[
            ForeclosureRecord(
                instrument_no=str(i), address=f"{i} St", grantor="Doe",
                sale_date=date(2026, 6, 3), pdf_link="https://x"
            )
            for i in range(10)
        ],
        cad_successes=9,
        tax_successes=9,
        failed_downloads=[],
        failed_cad=["bad_address"],
        failed_tax=["bad_address"],
        runtime_seconds=88.0,
    )
    assert report.overall_status in ("PASS", "REVIEW", "FAIL")
    assert report.total_results == 10
    assert report.records_processed == 10

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from scraper.pdf_extractor import PDFExtractor

SAMPLE_PDF_TEXT = """
NOTICE OF SUBSTITUTE TRUSTEE SALE

Instrument No.: 2026012345

Property: Commonly known as 1234 Oak Street, Austin, Texas 78701

Legal Description: LOT 5, BLOCK 12, SUNSET HILLS SUBDIVISION, TRAVIS COUNTY, TEXAS

Grantor: JOHN A. DOE AND MARY B. DOE

Grantee/Beneficiary: WELLS FARGO BANK, N.A.

Original Note Amount: $285,000.00

Deed of Trust Recorded: March 15, 2018, Instrument No. 2018045678

Substitute Trustee: Mortgage Solutions LLC, 1111 Law St, Austin TX 78702

Attorney/Returnee: Smith & Jones LLP, 2222 Legal Ave, Austin TX 78703

Sale Date: The first Tuesday of June 2026, being June 2, 2026 at 10:00 AM

Sale Location: Travis County Courthouse, Austin, Texas

Filed Date: 05/10/2026
"""


@pytest.fixture
def extractor():
    return PDFExtractor()


@pytest.fixture
def mock_pdf_path(tmp_path):
    pdf_file = tmp_path / "2026012345_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")
    return str(pdf_file)


def test_extract_instrument_no(extractor):
    result = extractor._extract_instrument_no(SAMPLE_PDF_TEXT, "2026012345_NOTICE.pdf")
    assert result == "2026012345"


def test_extract_address(extractor):
    result = extractor._extract_address(SAMPLE_PDF_TEXT)
    assert "1234 Oak Street" in result
    assert "Austin" in result


def test_extract_grantor(extractor):
    result = extractor._extract_grantor(SAMPLE_PDF_TEXT)
    assert "JOHN A. DOE" in result


def test_extract_grantee(extractor):
    result = extractor._extract_grantee(SAMPLE_PDF_TEXT)
    assert "WELLS FARGO" in result


def test_extract_sale_date(extractor):
    result = extractor._extract_sale_date(SAMPLE_PDF_TEXT)
    assert result is not None
    assert result.year == 2026
    assert result.month == 6


def test_extract_legal_description(extractor):
    result = extractor._extract_legal_description(SAMPLE_PDF_TEXT)
    assert "LOT 5" in result
    assert "SUNSET HILLS" in result


def test_extract_original_loan_amount(extractor):
    result = extractor._extract_loan_amount(SAMPLE_PDF_TEXT)
    assert "285,000" in result


def test_extract_deed_of_trust_recording(extractor):
    result = extractor._extract_dot_recording_no(SAMPLE_PDF_TEXT)
    assert "2018045678" in result


def test_extract_substitute_trustee(extractor):
    result = extractor._extract_substitute_trustee(SAMPLE_PDF_TEXT)
    assert "Mortgage Solutions" in result


def test_extract_attorney(extractor):
    result = extractor._extract_attorney(SAMPLE_PDF_TEXT)
    assert "Smith & Jones" in result


def test_extract_all_fields_returns_record(extractor, mock_pdf_path):
    with patch("pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_PDF_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        record = extractor.extract(mock_pdf_path, pdf_link="https://drive.google.com/file/abc")

    assert record.instrument_no == "2026012345"
    assert record.address is not None
    assert record.grantor is not None
    assert record.sale_date is not None
    assert record.pdf_link == "https://drive.google.com/file/abc"


def test_extract_handles_missing_fields(extractor, mock_pdf_path):
    sparse_text = "NOTICE OF SUBSTITUTE TRUSTEE SALE\nInstrument No.: 2026099999\nGrantor: JANE DOE\n"
    with patch("pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sparse_text
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        record = extractor.extract(mock_pdf_path, pdf_link="https://drive.google.com/file/abc")

    assert record is not None
    assert record.instrument_no == "2026099999"
    assert record.address == ""

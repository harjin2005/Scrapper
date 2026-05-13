import pytest
from datetime import date
from unittest.mock import MagicMock
from scraper.google_sheets import GoogleSheetsWriter
from scraper.models import ForeclosureRecord


@pytest.fixture
def config(tmp_path):
    from scraper.config import Config
    return Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="FOLDER123",
        google_credentials_path="config/credentials.json",
        google_token_path="config/token.json",
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )


@pytest.fixture
def sample_record():
    return ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Oak St, Austin TX 78701",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )


def test_is_duplicate_returns_true_when_found(config):
    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    existing = ["INDEX", "2026012345", "2026012346"]
    assert writer._is_duplicate("2026012345", existing) is True


def test_is_duplicate_returns_false_when_new(config):
    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    existing = ["2026011111", "2026022222"]
    assert writer._is_duplicate("2026033333", existing) is False


def test_sheet_headers():
    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    headers = writer.HEADERS
    assert "Instrument No." in headers
    assert "Address" in headers
    assert "Taxes Due" in headers
    assert "Appraised Value" in headers
    assert len(headers) == 23


def test_append_new_record(config, sample_record):
    mock_service = MagicMock()
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [["Index #", "Instrument No."], ["1", "2026099999"]]
    }
    mock_service.spreadsheets().values().append().execute.return_value = {}

    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    writer.service = mock_service

    result = writer.append_record(sample_record)
    assert result is True


def test_skip_duplicate_record(config, sample_record):
    mock_service = MagicMock()
    # Column B data: header row + one data row with the same instrument_no
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [["Instrument No."], ["2026012345"]]
    }

    writer = GoogleSheetsWriter.__new__(GoogleSheetsWriter)
    writer.config = config
    writer.service = mock_service

    result = writer.append_record(sample_record)
    assert result is False

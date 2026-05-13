import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from scraper.google_drive import GoogleDriveUploader


@pytest.fixture
def config(tmp_path):
    from scraper.config import Config
    creds = tmp_path / "creds.json"
    creds.write_text(
        '{"installed": {"client_id": "x", "client_secret": "y", '
        '"redirect_uris": ["http://localhost"], "auth_uri": "https://a.com", '
        '"token_uri": "https://b.com"}}'
    )
    return Config(
        clerk_portal_url="https://www.tccsearch.org/RealEstate/SearchEntry.aspx?e=newSession",
        cad_url="https://travis.prodigycad.com/property-search",
        tax_url="https://tax-office.traviscountytx.gov/properties/taxes/account-search",
        google_sheets_id="SHEET123",
        google_drive_folder_id="ROOT_FOLDER_ID",
        google_credentials_path=str(creds),
        google_token_path=str(tmp_path / "token.json"),
        downloads_dir=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )


def test_build_drive_path_for_date():
    uploader = GoogleDriveUploader.__new__(GoogleDriveUploader)
    path = uploader._build_drive_path(date(2026, 5, 13))
    assert path == "My Drive/Scrapping Task/Task 4: Travis County/PDFs/2026-05-13"


def test_get_shareable_link_format():
    uploader = GoogleDriveUploader.__new__(GoogleDriveUploader)
    link = uploader._make_shareable_link("FILE_ID_123")
    assert "FILE_ID_123" in link
    assert "drive.google.com" in link


def test_upload_file_calls_drive_api(config, tmp_path):
    pdf_path = tmp_path / "2026012345_NOTICE.pdf"
    pdf_path.write_bytes(b"PDF content")

    mock_service = MagicMock()
    mock_service.files().create().execute.return_value = {"id": "UPLOADED_FILE_ID"}
    mock_service.permissions().create().execute.return_value = {}

    uploader = GoogleDriveUploader.__new__(GoogleDriveUploader)
    uploader.service = mock_service
    uploader.config = config

    with patch.object(uploader, "_get_or_create_folder", return_value="DATED_FOLDER_ID"):
        link = uploader.upload(str(pdf_path), date(2026, 5, 13))

    assert "UPLOADED_FILE_ID" in link

import pytest
from datetime import date
from scraper.clerk_scraper import ClerkScraper


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


@pytest.mark.asyncio
async def test_build_date_range_current_month():
    scraper = ClerkScraper.__new__(ClerkScraper)
    from_date, to_date = scraper._build_date_range(date(2026, 5, 13))
    assert from_date == "05/01/2026"
    assert to_date == "05/13/2026"


@pytest.mark.asyncio
async def test_build_date_range_first_of_month():
    scraper = ClerkScraper.__new__(ClerkScraper)
    from_date, to_date = scraper._build_date_range(date(2026, 5, 1))
    assert from_date == "05/01/2026"
    assert to_date == "05/01/2026"


@pytest.mark.asyncio
async def test_get_dated_folder_path(tmp_path):
    scraper = ClerkScraper.__new__(ClerkScraper)
    scraper.downloads_dir = str(tmp_path)
    path = scraper._get_dated_download_path(date(2026, 5, 13))
    assert path.endswith("2026-05-13")


@pytest.mark.asyncio
async def test_pdf_filename_format():
    scraper = ClerkScraper.__new__(ClerkScraper)
    filename = scraper._build_pdf_filename("2026012345")
    assert filename == "2026012345_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"

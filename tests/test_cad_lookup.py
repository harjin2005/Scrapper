import pytest
from unittest.mock import AsyncMock, patch
from scraper.cad_lookup import CADLookup
from scraper.models import CADData


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


def _mock_playwright_context(mock_pw_class):
    mock_pw = AsyncMock()
    mock_pw_class.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_class.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_browser = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_page = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()
    return mock_pw, mock_browser, mock_page


@pytest.mark.asyncio
async def test_lookup_returns_full_cad_data_on_success(config):
    lookup = CADLookup(config)
    mock_data = CADData(
        uid="1070028210000",
        uid_raw="01070028210000",
        pid="771190",
        owner_name="EMMICK RYAN",
        appraised_value="537655",
        property_street="360 NUECES ST",
        property_state="TX",
        property_zip="78701",
        property_status="Yes",
        date_bought_by_owner="2021-06-04",
    )

    with patch("scraper.cad_lookup.async_playwright") as mock_pw_class:
        _mock_playwright_context(mock_pw_class)
        with patch.object(lookup, "_search", new=AsyncMock(return_value=mock_data)):
            result = await lookup.lookup("360 Nueces ST 3301, Austin TX 78701", None)

    assert result.uid == "1070028210000"
    assert result.uid_raw == "01070028210000"
    assert result.owner_name == "EMMICK RYAN"
    assert result.appraised_value == "537655"
    assert result.date_bought_by_owner == "2021-06-04"


@pytest.mark.asyncio
async def test_lookup_falls_back_to_grantor_when_no_uid(config):
    lookup = CADLookup(config)
    empty = CADData()
    mock_data = CADData(uid="1070028210000", owner_name="EMMICK RYAN")

    with patch("scraper.cad_lookup.async_playwright") as mock_pw_class:
        _mock_playwright_context(mock_pw_class)
        with patch.object(lookup, "_search", new=AsyncMock(side_effect=[empty, mock_data])):
            result = await lookup.lookup("", "EMMICK RYAN")

    assert result.uid == "1070028210000"


@pytest.mark.asyncio
async def test_lookup_returns_empty_cad_data_on_failure(config):
    lookup = CADLookup(config)

    with patch("scraper.cad_lookup.async_playwright") as mock_pw_class:
        _mock_playwright_context(mock_pw_class)
        with patch.object(lookup, "_search", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await lookup.lookup("360 Nueces ST", None)

    assert result is not None
    assert isinstance(result, CADData)
    assert result.uid is None

import pytest
from unittest.mock import AsyncMock, patch
from scraper.mls_lookup import MlsLookup


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
async def test_check_returns_yes_when_mls_site_in_results(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        _, _, mock_page = _mock_playwright_context(mock_pw_class)
        mock_page.goto = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=(
            "zillow.com 123 Main St Austin TX Home for Sale $450,000"
        ))

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "Yes"


@pytest.mark.asyncio
async def test_check_returns_yes_for_redfin(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        _, _, mock_page = _mock_playwright_context(mock_pw_class)
        mock_page.goto = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=(
            "redfin listing 123 Main St Austin TX"
        ))

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "Yes"


@pytest.mark.asyncio
async def test_check_returns_no_when_no_mls_sites(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        _, _, mock_page = _mock_playwright_context(mock_pw_class)
        mock_page.goto = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=(
            "Travis County Property Records 123 Main St deed transfer foreclosure"
        ))

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "No"


@pytest.mark.asyncio
async def test_check_returns_no_on_failure(config):
    lookup = MlsLookup(config)

    with patch("scraper.mls_lookup.async_playwright") as mock_pw_class:
        mock_pw = AsyncMock()
        mock_pw_class.return_value.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        mock_pw_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await lookup.check("123 Main St, Austin TX 78701")

    assert result == "No"


@pytest.mark.asyncio
async def test_check_empty_address_returns_no(config):
    lookup = MlsLookup(config)
    result = await lookup.check("")
    assert result == "No"

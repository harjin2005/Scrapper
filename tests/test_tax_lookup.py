import pytest
from unittest.mock import AsyncMock, patch
from scraper.tax_lookup import TaxLookup
from scraper.models import TaxData


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
async def test_lookup_returns_delinquent_tax(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="12500.00", years_delinquent=3)

    with patch.object(lookup, "_search_by_address", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St, Austin TX 78701", None)

    assert result.taxes_due == "12500.00"
    assert result.years_delinquent == 3


@pytest.mark.asyncio
async def test_lookup_returns_zero_when_current(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="0", years_delinquent=0)

    with patch.object(lookup, "_search_by_address", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", None)

    assert result.taxes_due == "0"


@pytest.mark.asyncio
async def test_lookup_returns_zero_on_failure(config):
    lookup = TaxLookup(config)

    with patch.object(lookup, "_search_by_address", new=AsyncMock(side_effect=Exception("connection refused"))):
        result = await lookup.lookup("1234 Oak St", None)

    assert result.taxes_due == "0"
    assert isinstance(result, TaxData)

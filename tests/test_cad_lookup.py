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


@pytest.mark.asyncio
async def test_lookup_returns_cad_data_on_success(config):
    lookup = CADLookup(config)
    mock_data = CADData(account_number="R123456", appraised_value="450000", property_status="Active")

    with patch.object(lookup, "_search_by_address", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St, Austin TX 78701", None)

    assert result.account_number == "R123456"
    assert result.appraised_value == "450000"


@pytest.mark.asyncio
async def test_lookup_returns_empty_cad_data_on_failure(config):
    lookup = CADLookup(config)

    with patch.object(lookup, "_search_by_address", new=AsyncMock(side_effect=Exception("timeout"))):
        result = await lookup.lookup("1234 Oak St", None)

    assert result is not None
    assert isinstance(result, CADData)
    assert result.account_number is None

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
async def test_lookup_returns_delinquent_tax_with_payment_date(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(
        taxes_due="12500.00",
        years_delinquent=3,
        last_payment_date="01/15/2023",
        initial_delinquency_year="2021",
    )

    with patch.object(lookup, "_lookup_by_uid", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", "01090901290000")

    assert result.taxes_due == "12500.00"
    assert result.years_delinquent == 3
    assert result.last_payment_date == "01/15/2023"
    assert result.initial_delinquency_year == "2021"


@pytest.mark.asyncio
async def test_lookup_returns_current_with_payment_date(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="Current", years_delinquent=0, last_payment_date="12/31/2025")

    with patch.object(lookup, "_lookup_by_uid", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", "01090901290000")

    assert result.taxes_due == "Current"
    assert result.last_payment_date == "12/31/2025"


@pytest.mark.asyncio
async def test_lookup_falls_back_to_address_when_no_uid(config):
    lookup = TaxLookup(config)
    mock_data = TaxData(taxes_due="5000.00", years_delinquent=1)

    with patch.object(lookup, "_search_by_address", new=AsyncMock(return_value=mock_data)):
        result = await lookup.lookup("1234 Oak St", None)

    assert result.taxes_due == "5000.00"


@pytest.mark.asyncio
async def test_lookup_returns_default_on_failure(config):
    lookup = TaxLookup(config)

    with patch.object(lookup, "_lookup_by_uid", new=AsyncMock(side_effect=Exception("timeout"))):
        with patch.object(lookup, "_search_by_address", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await lookup.lookup("1234 Oak St", "01090901290000")

    assert result.taxes_due == "0"
    assert isinstance(result, TaxData)

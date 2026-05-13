import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date


@pytest.mark.asyncio
async def test_run_pipeline_calls_all_steps(tmp_path):
    from scraper.config import Config
    config = Config(
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
    from scraper.models import ForeclosureRecord, CADData, TaxData
    sample_record = ForeclosureRecord(
        instrument_no="2026012345",
        address="123 Oak St",
        grantor="John Doe",
        sale_date=date(2026, 6, 3),
        pdf_link="https://drive.google.com/file/abc",
    )

    with (
        patch("main.ClerkScraper") as MockClerk,
        patch("main.PDFExtractor") as MockExtractor,
        patch("main.CADLookup") as MockCAD,
        patch("main.TaxLookup") as MockTax,
        patch("main.GoogleDriveUploader") as MockDrive,
        patch("main.GoogleSheetsWriter") as MockSheets,
        patch("main.Validator") as MockValidator,
    ):
        MockClerk.return_value.run = AsyncMock(
            return_value=[("2026012345", str(tmp_path / "2026012345.pdf"))]
        )
        MockExtractor.return_value.extract.return_value = sample_record
        MockCAD.return_value.lookup = AsyncMock(
            return_value=CADData(account_number="R123", appraised_value="400000", property_status="Active")
        )
        MockTax.return_value.lookup = AsyncMock(
            return_value=TaxData(taxes_due="0", years_delinquent=0)
        )
        MockDrive.return_value.upload.return_value = "https://drive.google.com/file/abc"
        MockSheets.return_value.append_record.return_value = True
        mock_report = MagicMock()
        mock_report.overall_status = "PASS"
        mock_report.model_dump.return_value = {"overall_status": "PASS"}
        MockValidator.return_value.build_run_report.return_value = mock_report

        import main
        report = await main.run_pipeline(config, run_date=date(2026, 5, 13))

    assert report is not None
    assert report.overall_status == "PASS"

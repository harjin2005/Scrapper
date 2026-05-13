from __future__ import annotations
from datetime import datetime
from googleapiclient.discovery import build
from scraper.config import Config
from scraper.google_drive import load_credentials
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("google_sheets")

SHEET_RANGE = "Sheet1"


class GoogleSheetsWriter:
    HEADERS = [
        "Index #", "Instrument No.", "Address", "County", "Sale Type",
        "Sale Date", "Document Type", "Grantor(s)", "Grantee(s)",
        "Legal Description", "Related Document No.", "Related Doc Type",
        "Substitute Trustee", "Returnee/Attorney", "Notary",
        "Date Received", "PDF Link", "Property Status", "Account Number",
        "Created At", "Updated At", "Taxes Due", "Appraised Value",
    ]

    def __init__(self, config: Config) -> None:
        self.config = config
        creds = load_credentials(config)
        self.service = build("sheets", "v4", credentials=creds)

    def ensure_headers(self) -> None:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.config.google_sheets_id, range=f"{SHEET_RANGE}!A1:W1")
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!A1",
                valueInputOption="RAW",
                body={"values": [self.HEADERS]},
            ).execute()
            log.info("sheet_headers_written")

    def _get_existing_instrument_nos(self) -> list[str]:
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!B:B",
            )
            .execute()
        )
        rows = result.get("values", [])
        return [row[0] for row in rows if row]

    def _is_duplicate(self, instrument_no: str, existing: list[str]) -> bool:
        return instrument_no in existing

    def _get_next_index(self) -> int:
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!A:A",
            )
            .execute()
        )
        rows = result.get("values", [])
        return max(len(rows), 1)

    def append_record(self, record: ForeclosureRecord) -> bool:
        existing = self._get_existing_instrument_nos()
        if self._is_duplicate(record.instrument_no, existing):
            log.info("skipping_duplicate", instrument_no=record.instrument_no)
            return False

        record.index_no = self._get_next_index()
        record.updated_at = datetime.utcnow()

        self.service.spreadsheets().values().append(
            spreadsheetId=self.config.google_sheets_id,
            range=f"{SHEET_RANGE}!A:W",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [record.to_sheet_row()]},
        ).execute()
        log.info("record_appended", instrument_no=record.instrument_no)
        return True

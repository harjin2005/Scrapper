from __future__ import annotations
from datetime import datetime
from googleapiclient.discovery import build
from scraper.config import Config
from scraper.google_drive import load_credentials
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("google_sheets")

SHEET_RANGE = "Sheet1"

# Column X (index 23) = UID. Last column AP (index 41) = Listed on MLS.
_UID_COL   = "X"
_LAST_COL  = "AP"


class GoogleSheetsWriter:
    HEADERS = [
        # Existing columns A-W (23 cols, indexes 0-22)
        "Index #", "Instrument No.", "Address", "County", "Sale Type",
        "Sale Date", "Document Type", "Grantor(s)", "Grantee(s)",
        "Legal Description", "Related Document No.", "Related Doc Type",
        "Substitute Trustee", "Returnee/Attorney", "Notary",
        "Date Received", "PDF Link", "Property Status", "Account Number",
        "Created At", "Updated At", "Taxes Due", "Appraised Value",
        # New columns X-AP (19 cols, indexes 23-41)
        "UID", "Owner Name (CAD)", "Owner Secondary",
        "Property Street", "Property City", "Property State", "Property Zip",
        "Mailing Street", "Mailing City", "Mailing State", "Mailing Zip",
        "Property Type Code", "Acreage", "Legal Description (CAD)",
        "Date Bought By Owner", "Years Delinquent",
        "Last Payment Date", "Initial Delinquency Year", "Listed on MLS",
    ]

    def __init__(self, config: Config) -> None:
        self.config = config
        creds = load_credentials(config)
        self.service = build("sheets", "v4", credentials=creds)

    def ensure_headers(self) -> None:
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!A1:{_LAST_COL}1",
            )
            .execute()
        )
        existing = result.get("values", [[]])[0] if result.get("values") else []
        if existing == self.HEADERS:
            return  # already up to date
        # Write/overwrite headers (handles both fresh sheet and stale 23-col header)
        self.service.spreadsheets().values().update(
            spreadsheetId=self.config.google_sheets_id,
            range=f"{SHEET_RANGE}!A1",
            valueInputOption="RAW",
            body={"values": [self.HEADERS]},
        ).execute()
        log.info("sheet_headers_written", col_count=len(self.HEADERS))

    def get_existing_uids(self) -> set[str]:
        """Return set of UID values already in the sheet (column X)."""
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.google_sheets_id,
                range=f"{SHEET_RANGE}!{_UID_COL}:{_UID_COL}",
            )
            .execute()
        )
        rows = result.get("values", [])
        return {row[0] for row in rows if row and row[0]}

    def _is_duplicate(self, instrument_no: str, existing: list[str]) -> bool:
        return instrument_no in existing

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

    def _get_sheet_id(self) -> int:
        meta = self.service.spreadsheets().get(
            spreadsheetId=self.config.google_sheets_id
        ).execute()
        for s in meta.get("sheets", []):
            if s["properties"]["title"] == SHEET_RANGE:
                return s["properties"]["sheetId"]
        return 0

    def _apply_black_font(self, row_index: int) -> None:
        """Force black font on a just-appended data row (row_index is 0-based)."""
        sheet_id = self._get_sheet_id()
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.config.google_sheets_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 42,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "foregroundColor": {"red": 0, "green": 0, "blue": 0},
                                "bold": False,
                            },
                            "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            }]},
        ).execute()

    def append_record(self, record: ForeclosureRecord) -> bool:
        existing = self._get_existing_instrument_nos()
        if record.instrument_no in existing:
            log.info("skipping_duplicate_instrument", instrument_no=record.instrument_no)
            return False

        record.index_no = self._get_next_index()
        record.updated_at = datetime.utcnow()

        self.service.spreadsheets().values().append(
            spreadsheetId=self.config.google_sheets_id,
            range=f"{SHEET_RANGE}!A:{_LAST_COL}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [record.to_sheet_row()]},
        ).execute()

        # Row index = record.index_no (1-based index_no, 0-based row = index_no itself since row 0 = header)
        self._apply_black_font(record.index_no)

        log.info("record_appended", instrument_no=record.instrument_no)
        return True

from __future__ import annotations
import time
from datetime import datetime, timedelta
from typing import Set
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from scraper.config import Config
from scraper.google_drive import load_credentials
from scraper.models import ForeclosureRecord
from scraper.logger import get_logger

log = get_logger("google_sheets")


def _gapi_execute(request):
    """Execute a Google API request with retry on 429/5xx; fail fast on 403/401."""
    for attempt in range(4):
        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status
            if status == 403:
                log.error("google_api_forbidden", status=status)
                raise
            if status in (429, 500, 503) and attempt < 3:
                wait = 4 * (2 ** attempt)
                log.warning("google_api_retry", status=status, wait_seconds=wait, attempt=attempt + 1)
                time.sleep(wait)
                continue
            raise

class GoogleSheetsWriter:
    HEADERS = [
        "UID",
        "Property County",
        "Property Owner Name",
        "Secondary / Business Owner",
        "Property Street",
        "Property City",
        "Property State",
        "Property Zip",
        "Mailing Street",
        "Mailing City",
        "Mailing State",
        "Mailing Zip",
        "Appraised Value",
        "Total Due",
        "Property Type Code",
        "Property Type",
        "Legal Description",
        "Acreage (Lot Size)",
        "AG Taxable Value",
        "Last Tax Payment Date",
        "Initial Delinquency Year",
        "Cause # (Tax Lawsuit #)",
        "Cause # (Tax Lawsuit #) Date Filed",
        "Probate Case #",
        "Bankruptcy #",
        "Divorce #",
        "Relevant Doc/ Doc Links",
        "Is it listed on MLS (Zillow/Redfin/etc.)?",
        "Sale Date (for Tax Sale)",
        "Date bought (by Current Owner)",
        "Owner Deceased?",
        "Occupancy Status",
        "Property Condition",
        "Instrument No (Internal Dedup)",
        "Date Received (Internal Grouping)"
    ]

    def __init__(self, config: Config) -> None:
        self.config = config
        creds = load_credentials(config)
        self.service = build("sheets", "v4", credentials=creds)
        self._existing_instruments: Set[str] = set()
        self._known_sheets: dict[str, int] = {}
        self._initialized = False

    def _init_cache(self) -> None:
        if self._initialized:
            return
            
        # Get all sheets
        meta = _gapi_execute(
            self.service.spreadsheets().get(spreadsheetId=self.config.google_sheets_id)
        )
        self._known_sheets = {
            s["properties"]["title"]: s["properties"]["sheetId"]
            for s in meta.get("sheets", [])
        }
        
        # Load all existing instrument numbers from all sheets (Column AH = 34th column)
        ranges = [f"'{title}'!AH:AH" for title in self._known_sheets.keys()]
        if ranges:
            # batchGet has a limit on number of ranges, but should be fine for <100 sheets
            # For safety, chunk ranges if needed. Here we assume small number of sheets.
            try:
                batch_res = _gapi_execute(
                    self.service.spreadsheets().values().batchGet(
                        spreadsheetId=self.config.google_sheets_id,
                        ranges=ranges
                    )
                )
                for val_range in batch_res.get("valueRanges", []):
                    for row in val_range.get("values", []):
                        if row and row[0] and row[0] != "Instrument No (Internal Dedup)":
                            self._existing_instruments.add(str(row[0]).strip())
            except HttpError as e:
                log.warning("batch_get_failed", error=str(e))
                
        self._initialized = True

    def _get_week_tab_name(self, record: ForeclosureRecord) -> str:
        # Determine the date to use
        date_obj = None
        if record.date_received:
            date_obj = record.date_received
        else:
            date_obj = record.created_at.date()
            
        # Find Monday of that week
        monday = date_obj - timedelta(days=date_obj.weekday())
        sunday = monday + timedelta(days=6)
        
        # Format: "Jun 21 - Jun 27"
        # Windows strftime doesn't support %-d, so use manual strip or replace
        mon_str = monday.strftime("%b %d").replace(" 0", " ")
        sun_str = sunday.strftime("%b %d").replace(" 0", " ")
        return f"{mon_str} - {sun_str}"

    def _ensure_tab_exists(self, tab_name: str) -> None:
        self._init_cache()
        if tab_name in self._known_sheets:
            return
            
        # Create sheet
        log.info("creating_new_tab", tab_name=tab_name)
        create_res = _gapi_execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.config.google_sheets_id,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {
                                    "title": tab_name
                                }
                            }
                        }
                    ]
                }
            )
        )
        new_sheet_id = create_res["replies"][0]["addSheet"]["properties"]["sheetId"]
        self._known_sheets[tab_name] = new_sheet_id
        
        # Apply headers
        _gapi_execute(
            self.service.spreadsheets().values().update(
                spreadsheetId=self.config.google_sheets_id,
                range=f"'{tab_name}'!A1",
                valueInputOption="RAW",
                body={"values": [self.HEADERS]},
            )
        )
        
        # Make headers bold
        _gapi_execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.config.google_sheets_id,
                body={
                    "requests": [
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": new_sheet_id,
                                    "startRowIndex": 0,
                                    "endRowIndex": 1,
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "textFormat": {"bold": True}
                                    }
                                },
                                "fields": "userEnteredFormat.textFormat.bold",
                            }
                        }
                    ]
                }
            )
        )

    def append_record(self, record: ForeclosureRecord) -> bool:
        self._init_cache()
        
        if record.instrument_no in self._existing_instruments:
            log.info("skipping_duplicate_instrument", instrument_no=record.instrument_no)
            return False

        tab_name = self._get_week_tab_name(record)
        self._ensure_tab_exists(tab_name)

        _gapi_execute(
            self.service.spreadsheets().values().append(
                spreadsheetId=self.config.google_sheets_id,
                range=f"'{tab_name}'!A:A",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [record.to_sheet_row()]},
            )
        )

        self._existing_instruments.add(record.instrument_no)
        log.info("record_appended_to_week", instrument_no=record.instrument_no, tab=tab_name)
        return True

from __future__ import annotations
from typing import Optional
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from montgomery.models import DelinquentRecord
from scraper.logger import get_logger

log = get_logger("sheets_writer")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

HEADERS = [
    "Account Number",
    "Property Owner",
    "Property Address",
    "Mailing Address",
    "Property Type",
    "Property Type Code",
    "Lot Size",
    "Legal Description",
    "Owner Contact Number",
    "Email",
    "Last Tax Payment Date",
    "Initial Delinquency Year",
    "Years Behind Taxes",
    "Cause / Lawsuit No",
    "Cause Date",
    "Appraised Value",
    "Total Tax Due",
    "County",
    "Excel File Date",
    "Created At",
    "Updated At",
]


class SheetsWriter:
    def __init__(
        self,
        spreadsheet_id: str,
        credentials_path: str,
        token_path: str,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self._creds_path = credentials_path
        self._token_path = token_path
        self._service = None
        self._sheet_name = "Montgomery"

    def _get_service(self):
        if self._service:
            return self._service
        creds = None
        token = Path(self._token_path)
        if token.exists():
            creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._creds_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(token, "w") as f:
                f.write(creds.to_json())
        self._service = build("sheets", "v4", credentials=creds)
        return self._service

    def _ensure_sheet_exists(self) -> None:
        """Create the Montgomery tab if it doesn't exist."""
        svc = self._get_service()
        meta = svc.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if self._sheet_name not in existing:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": self._sheet_name}}}]},
            ).execute()
            log.info("sheet_tab_created", name=self._sheet_name)

    def _ensure_headers(self) -> None:
        self._ensure_sheet_exists()
        svc = self._get_service()
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=f"{self._sheet_name}!1:1")
            .execute()
        )
        rows = result.get("values", [])
        if not rows or rows[0] != HEADERS:
            svc.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self._sheet_name}!A1",
                valueInputOption="RAW",
                body={"values": [HEADERS]},
            ).execute()
            log.info("headers_written", sheet=self._sheet_name)

    def _get_existing_account_numbers(self) -> dict[str, int]:
        """Return {account_number: row_index_1based} for all existing rows."""
        svc = self._get_service()
        result = (
            svc.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self._sheet_name}!A:A",
            )
            .execute()
        )
        rows = result.get("values", [])
        # Row 1 = headers, data starts at row 2
        mapping: dict[str, int] = {}
        for i, row in enumerate(rows[1:], start=2):
            if row:
                mapping[str(row[0]).strip()] = i
        return mapping

    def upsert(self, record: DelinquentRecord) -> str:
        """Insert or update one record. Returns 'added' or 'updated'."""
        self._ensure_headers()
        existing = self._get_existing_account_numbers()
        row_data = record.to_sheet_row()

        if record.account_number in existing:
            row_idx = existing[record.account_number]
            range_notation = f"{self._sheet_name}!A{row_idx}"
            self._get_service().spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_notation,
                valueInputOption="RAW",
                body={"values": [row_data]},
            ).execute()
            log.info("row_updated", account=record.account_number, row=row_idx)
            return "updated"
        else:
            self._get_service().spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self._sheet_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row_data]},
            ).execute()
            log.info("row_added", account=record.account_number)
            return "added"

    def upsert_batch(self, records: list[DelinquentRecord]) -> tuple[int, int]:
        """Upsert all records. Returns (added_count, updated_count)."""
        self._ensure_headers()
        existing = self._get_existing_account_numbers()

        to_update: list[tuple[int, list]] = []
        to_append: list[list] = []

        for rec in records:
            row_data = rec.to_sheet_row()
            if rec.account_number in existing:
                to_update.append((existing[rec.account_number], row_data))
            else:
                to_append.append(row_data)

        svc = self._get_service()

        # Batch update existing rows
        if to_update:
            data = [
                {
                    "range": f"{self._sheet_name}!A{row_idx}",
                    "values": [row_data],
                }
                for row_idx, row_data in to_update
            ]
            svc.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": data},
            ).execute()
            log.info("batch_updated", count=len(to_update))

        # Append new rows
        if to_append:
            svc.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self._sheet_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": to_append},
            ).execute()
            log.info("batch_appended", count=len(to_append))

        return len(to_append), len(to_update)

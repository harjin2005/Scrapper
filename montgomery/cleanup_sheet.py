"""
One-shot script: delete rows from the Montgomery Sheet that are NOT in the Excel file
(i.e. fake/test rows). Prints what will be deleted and asks for confirmation.
"""
from __future__ import annotations
import sys
import pandas as pd
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SPREADSHEET_ID = "1PE534MXnwlRqQoiukX8fCvtwamiKnT4JaiRsbBOb3DM"
SHEET_NAME = "Montgomery"
XLSX = "montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx"
CREDS_PATH = "config/credentials.json"
TOKEN_PATH = "config/token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_service():
    creds = None
    token = Path(TOKEN_PATH)
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def main():
    print("Loading Excel CAN list...")
    df = pd.read_excel(XLSX, header=2, dtype=str, usecols=["CAN"])
    valid_cans = set(df["CAN"].dropna().str.strip().tolist())
    print(f"  {len(valid_cans)} valid CANs in Excel")

    svc = get_service()
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A:C")
        .execute()
    )
    rows = result.get("values", [])
    print(f"  {len(rows)} rows in Sheet (including header)")

    # Find rows to delete (account number not in Excel AND not header)
    to_delete: list[tuple[int, str, str]] = []  # (row_1based, acct, owner)
    for i, row in enumerate(rows):
        if i == 0:
            continue  # skip header
        acct = str(row[0]).strip() if row else ""
        owner = str(row[1]).strip() if len(row) > 1 else ""
        if acct and acct not in valid_cans:
            to_delete.append((i + 1, acct, owner))  # 1-based row index

    if not to_delete:
        print("No fake rows found. Sheet is clean.")
        return

    print(f"\nRows to DELETE ({len(to_delete)}):")
    for row_idx, acct, owner in to_delete:
        print(f"  Row {row_idx}: account={acct}  owner={owner}")

    print("\nDeleting...")
    # Must delete from bottom to top to preserve row indices
    requests = []
    for row_idx, acct, owner in sorted(to_delete, key=lambda x: x[0], reverse=True):
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": _get_sheet_id(svc),
                    "dimension": "ROWS",
                    "startIndex": row_idx - 1,  # 0-based
                    "endIndex": row_idx,
                }
            }
        })

    svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()
    print(f"Deleted {len(to_delete)} rows.")


def _get_sheet_id(svc) -> int:
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == SHEET_NAME:
            return s["properties"]["sheetId"]
    raise ValueError(f"Sheet '{SHEET_NAME}' not found")


if __name__ == "__main__":
    main()

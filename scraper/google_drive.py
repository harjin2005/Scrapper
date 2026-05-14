from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from scraper.config import Config
from scraper.logger import get_logger

log = get_logger("google_drive")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]


def load_credentials(config: Config) -> Credentials:
    creds = None
    token_path = config.google_token_path
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(config.google_credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


class GoogleDriveUploader:
    TASK_FOLDER_PATH = ["Scrapping Task", "Task 4: Travis County", "PDFs"]

    def __init__(self, config: Config) -> None:
        self.config = config
        creds = load_credentials(config)
        self.service = build("drive", "v3", credentials=creds)

    def _build_drive_path(self, run_date: date) -> str:
        date_str = run_date.strftime("%Y-%m-%d")
        return f"My Drive/{'/'.join(self.TASK_FOLDER_PATH)}/{date_str}"

    def _make_shareable_link(self, file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

    def _get_or_create_folder(self, parent_id: str, folder_name: str) -> str:
        query = (
            f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=meta, fields="id").execute()
        return folder["id"]

    def _find_existing_file(self, folder_id: str, filename: str) -> Optional[str]:
        query = (
            f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def upload(self, pdf_path: str, run_date: date) -> str:
        dated_folder_id = self._get_dated_folder(run_date)
        filename = Path(pdf_path).name

        existing_id = self._find_existing_file(dated_folder_id, filename)
        if existing_id:
            log.info("pdf_already_on_drive", filename=filename, file_id=existing_id)
            return self._make_shareable_link(existing_id)

        file_metadata = {"name": filename, "parents": [dated_folder_id]}
        media = MediaFileUpload(pdf_path, mimetype="application/pdf")
        uploaded = (
            self.service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        file_id = uploaded["id"]
        self.service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
        link = self._make_shareable_link(file_id)
        log.info("pdf_uploaded_to_drive", filename=filename, file_id=file_id)
        return link

    def _get_dated_folder(self, run_date: date) -> str:
        parent_id = self.config.google_drive_folder_id
        for folder_name in self.TASK_FOLDER_PATH:
            parent_id = self._get_or_create_folder(parent_id, folder_name)
        date_folder = run_date.strftime("%Y-%m-%d")
        return self._get_or_create_folder(parent_id, date_folder)

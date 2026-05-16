from __future__ import annotations
from pathlib import Path
from datetime import date
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from scraper.logger import get_logger

log = get_logger("drive_uploader_montgomery")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_MIMETYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class DriveUploader:
    def __init__(
        self,
        folder_id: str,
        credentials_path: str,
        token_path: str,
    ) -> None:
        self.folder_id = folder_id
        self._creds_path = credentials_path
        self._token_path = token_path
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        creds = None
        token = Path(self._token_path)
        if token.exists():
            with open(token, "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._creds_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(token, "wb") as f:
                pickle.dump(creds, f)
        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _get_or_create_subfolder(self, name: str, parent_id: str) -> str:
        svc = self._get_service()
        query = (
            f"name='{name}' and '{parent_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
        )
        results = svc.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = svc.files().create(body=meta, fields="id").execute()
        log.info("drive_folder_created", name=name, parent=parent_id)
        return folder["id"]

    def _find_existing_file(self, folder_id: str, filename: str) -> str | None:
        svc = self._get_service()
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        results = svc.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def _make_shareable(self, file_id: str) -> str:
        svc = self._get_service()
        svc.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
        return f"https://drive.google.com/file/d/{file_id}/view"

    def upload(self, xlsx_path: str, run_date: date | None = None) -> str:
        """Upload XLSX to Drive, return shareable link. Skips if already uploaded."""
        if run_date is None:
            run_date = date.today()

        # Subfolder: YYYY-MM-DD
        dated_folder_name = run_date.strftime("%Y-%m-%d")
        dated_folder_id = self._get_or_create_subfolder(dated_folder_name, self.folder_id)

        filename = Path(xlsx_path).name
        existing_id = self._find_existing_file(dated_folder_id, filename)
        if existing_id:
            log.info("excel_already_on_drive", filename=filename, file_id=existing_id)
            return self._make_shareable(existing_id)

        svc = self._get_service()
        meta = {"name": filename, "parents": [dated_folder_id]}
        media = MediaFileUpload(xlsx_path, mimetype=_MIMETYPE_XLSX, resumable=True)
        uploaded = (
            svc.files()
            .create(body=meta, media_body=media, fields="id")
            .execute()
        )
        file_id = uploaded["id"]
        link = self._make_shareable(file_id)
        size_kb = Path(xlsx_path).stat().st_size // 1024
        log.info("excel_uploaded_to_drive", filename=filename, size_kb=size_kb, link=link)
        return link

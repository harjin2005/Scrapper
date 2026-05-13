from __future__ import annotations
import os
from pathlib import Path
import yaml
from pydantic import BaseModel


class Config(BaseModel):
    clerk_portal_url: str
    cad_url: str
    tax_url: str
    google_sheets_id: str
    google_drive_folder_id: str
    google_credentials_path: str
    google_token_path: str
    downloads_dir: str
    logs_dir: str
    search_doc_type: str = "NOTICE OF SUBSTITUTE TRUSTEE SALE"
    retry_attempts: int = 3
    request_timeout_ms: int = 30000
    headless: bool = True


_CONFIG: Config | None = None


def load_config(path: str | None = None) -> Config:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    config_path = path or os.environ.get(
        "SCRAPER_CONFIG", str(Path(__file__).parent.parent / "config" / "config.yaml")
    )
    with open(config_path) as f:
        data = yaml.safe_load(f)
    _CONFIG = Config(**data)
    return _CONFIG

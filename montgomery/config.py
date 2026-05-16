from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Config:
    # Montgomery County sites
    tax_forms_url: str
    mcad_url: str
    tax_office_url: str

    # Google
    google_sheets_id: str
    google_drive_folder_id: str
    google_credentials_path: str
    google_token_path: str

    # Storage
    downloads_dir: str
    logs_dir: str
    checkpoint_dir: str

    # Runtime
    retry_attempts: int = 3
    request_timeout_ms: int = 30000
    headless: bool = False
    rate_limit_delay_seconds: float = 2.0
    checkpoint_every_n: int = 100


def load_config(path: str = "montgomery/config/config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(**data)

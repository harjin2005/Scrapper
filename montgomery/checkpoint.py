from __future__ import annotations
import json
from pathlib import Path
from scraper.logger import get_logger

log = get_logger("checkpoint")


class Checkpoint:
    """Tracks processed account numbers. Saves every N records. Resume on crash."""

    def __init__(self, checkpoint_dir: str, excel_file_date: str) -> None:
        Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
        safe_date = excel_file_date.replace("/", "-").replace(" ", "_")
        self._path = Path(checkpoint_dir) / f"checkpoint_{safe_date}.json"
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                raw = json.load(f)
            # Migrate list → set for O(1) lookup (old checkpoints stored a list)
            done = raw.get("done", [])
            if isinstance(done, list):
                raw["done"] = set(done)
            log.info("checkpoint_loaded", path=str(self._path), processed=len(raw["done"]))
            return raw
        return {"done": set(), "excel_file_date": ""}

    def save(self) -> None:
        # Serialize set as sorted list for stable JSON
        serialisable = {**self._data, "done": sorted(self._data["done"])}
        with open(self._path, "w") as f:
            json.dump(serialisable, f)

    def mark_done(self, account_number: str) -> None:
        self._data["done"].add(account_number)

    def is_done(self, account_number: str) -> bool:
        return account_number in self._data["done"]

    def done_count(self) -> int:
        return len(self._data["done"])

    def reset(self) -> None:
        self._data = {"done": set(), "excel_file_date": ""}
        self.save()
        log.info("checkpoint_reset", path=str(self._path))

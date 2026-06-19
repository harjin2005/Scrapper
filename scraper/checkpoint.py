from __future__ import annotations
import json
from pathlib import Path
from scraper.logger import get_logger

log = get_logger("checkpoint")


class CheckpointManager:
    """
    Three-stage resume for Travis County pipeline.
    Stage 1: clerk scrape results (saved once, reused on resume to skip clerk run).
    Stage 2: per-record completion (marked after successful Sheets write).
    """

    def __init__(self, checkpoints_dir: str, run_date: str) -> None:
        Path(checkpoints_dir).mkdir(parents=True, exist_ok=True)
        self._path = Path(checkpoints_dir) / f"{run_date}.json"
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                raw = json.load(f)
            done = raw.get("done", [])
            if isinstance(done, list):
                raw["done"] = set(done)
            log.info("checkpoint_loaded", path=str(self._path), done=len(raw["done"]))
            return raw
        return {"listings": None, "done": set()}

    def save(self) -> None:
        serializable = {**self._data, "done": sorted(self._data["done"])}
        with open(self._path, "w") as f:
            json.dump(serializable, f, default=str)
        log.info("checkpoint_saved", path=str(self._path), done=len(self._data["done"]))

    def save_listings(self, entries: list) -> None:
        self._data["listings"] = [e.model_dump(mode="json") for e in entries]
        self.save()

    def load_listings(self):
        raw = self._data.get("listings")
        if raw is None:
            return None
        from scraper.models import ListingEntry
        return [ListingEntry(**e) for e in raw]

    def is_done(self, instrument_no: str) -> bool:
        return instrument_no in self._data["done"]

    def mark_done(self, instrument_no: str) -> None:
        self._data["done"].add(instrument_no)

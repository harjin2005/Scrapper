from __future__ import annotations
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from scraper.logger import get_logger

log = get_logger("excel_downloader")

DELINQUENT_ROLL_PATTERN = re.compile(
    r"Delinquent\s+Tax\s+Roll\s*[-–]\s*Detail\s+as\s+of\s+([\w\s,]+\d{4})",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_last_processed_date(downloads_dir: str) -> Optional[str]:
    """Read the most recently downloaded file's date from a tracking file."""
    tracking = Path(downloads_dir) / "last_processed_date.txt"
    if tracking.exists():
        return tracking.read_text().strip()
    return None


def save_last_processed_date(downloads_dir: str, date_str: str) -> None:
    Path(downloads_dir).mkdir(parents=True, exist_ok=True)
    (Path(downloads_dir) / "last_processed_date.txt").write_text(date_str)


def check_for_new_file(tax_forms_url: str, downloads_dir: str) -> Optional[tuple[str, str]]:
    """
    Check county website for new Delinquent Tax Roll.
    Returns (download_url, as_of_date) if new file found, else None.
    """
    log.info("checking_for_new_excel_file", url=tax_forms_url)
    try:
        resp = requests.get(tax_forms_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        log.error("tax_forms_page_fetch_failed", error=str(exc))
        raise

    html = resp.text

    # Find all Delinquent Tax Roll links with their "as of" dates
    # Look for anchor tags containing the text pattern
    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*)["\'][^>]*>\s*Delinquent\s+Tax\s+Roll\s*[-–]\s*Detail\s+as\s+of\s+([\w\s,]+\d{4})[^<]*</a>',
        re.IGNORECASE,
    )

    matches = link_pattern.findall(html)

    if not matches:
        # Fallback: find href near the text
        href_pattern = re.compile(
            r'href=["\']([^"\']+\.xlsx[^"\']*)["\']',
            re.IGNORECASE,
        )
        date_match = DELINQUENT_ROLL_PATTERN.search(html)
        href_match = href_pattern.search(html)

        if date_match and href_match:
            as_of_date = date_match.group(1).strip()
            href = href_match.group(1)
            matches = [(href, as_of_date)]
        else:
            log.warning("delinquent_roll_link_not_found")
            return None

    # Use first/latest match
    href, as_of_date = matches[0]
    as_of_date = as_of_date.strip()

    # Build full URL if relative
    if href.startswith("http"):
        download_url = href
    else:
        base = "https://www.mctotx.org"
        download_url = base + href if href.startswith("/") else base + "/" + href

    log.info("delinquent_roll_found", as_of_date=as_of_date, url=download_url)

    # Check if this is newer than last processed
    last_date = get_last_processed_date(downloads_dir)
    if last_date and last_date == as_of_date:
        log.info("no_new_file", last_processed=last_date)
        return None

    log.info("new_file_detected", previous=last_date, current=as_of_date)
    return download_url, as_of_date


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def download_excel(download_url: str, as_of_date: str, downloads_dir: str) -> str:
    """Download Excel file, return local path."""
    Path(downloads_dir).mkdir(parents=True, exist_ok=True)

    # Build filename from date: "May 11, 2026" → "2026-05-11"
    try:
        dt = datetime.strptime(as_of_date.strip(), "%B %d, %Y")
        date_slug = dt.strftime("%Y-%m-%d")
    except ValueError:
        date_slug = re.sub(r"[^\w]", "_", as_of_date)

    filename = f"Montgomery_Delinquent_Tax_Roll_{date_slug}.xlsx"
    dest = Path(downloads_dir) / filename

    if dest.exists():
        log.info("excel_already_downloaded", path=str(dest))
        return str(dest)

    log.info("downloading_excel", url=download_url, dest=str(dest))
    resp = requests.get(download_url, headers=HEADERS, timeout=120, stream=True)
    resp.raise_for_status()

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    size_kb = dest.stat().st_size // 1024
    log.info("excel_downloaded", filename=filename, size_kb=size_kb)
    return str(dest)

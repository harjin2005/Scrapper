from __future__ import annotations
import asyncio
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright
from scraper.logger import get_logger

log = get_logger("excel_downloader")

_BASE_URL = "https://www.mctotx.org"
_TAX_FORMS_URL = _BASE_URL + "/property/property_tax_forms.php"

DELINQUENT_ROLL_PATTERN = re.compile(
    r"Delinquent\s+Tax\s+Roll\s*[-–]\s*Detail\s+as\s+of\s+([\w\s,]+\d{4})",
    re.IGNORECASE,
)

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _TAX_FORMS_URL,
}


def get_last_processed_date(downloads_dir: str) -> Optional[str]:
    tracking = Path(downloads_dir) / "last_processed_date.txt"
    if tracking.exists():
        return tracking.read_text().strip()
    return None


def save_last_processed_date(downloads_dir: str, date_str: str) -> None:
    Path(downloads_dir).mkdir(parents=True, exist_ok=True)
    (Path(downloads_dir) / "last_processed_date.txt").write_text(date_str)


async def _fetch_page_with_playwright(url: str) -> str:
    """Use Playwright to load page — handles JS challenges and cookies."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            html = await page.content()
            return html
        finally:
            await browser.close()


async def check_for_new_file(tax_forms_url: str, downloads_dir: str) -> Optional[tuple[str, str]]:
    """
    Check county website for new Delinquent Tax Roll.
    Returns (download_url, as_of_date) if new file found, else None.
    Uses Playwright to bypass bot detection.
    """
    log.info("checking_for_new_excel_file", url=tax_forms_url)

    try:
        html = await _fetch_page_with_playwright(tax_forms_url)
    except Exception as exc:
        log.error("tax_forms_page_fetch_failed", error=str(exc))
        raise

    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*)["\'][^>]*>\s*Delinquent\s+Tax\s+Roll\s*[-–]\s*Detail\s+as\s+of\s+([\w\s,]+\d{4})[^<]*</a>',
        re.IGNORECASE,
    )
    matches = link_pattern.findall(html)

    if not matches:
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

    href, as_of_date = matches[0]
    as_of_date = as_of_date.strip()

    if href.startswith("http"):
        download_url = href
    else:
        download_url = _BASE_URL + href if href.startswith("/") else _BASE_URL + "/" + href

    log.info("delinquent_roll_found", as_of_date=as_of_date, url=download_url)

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
    resp = requests.get(download_url, headers=DOWNLOAD_HEADERS, timeout=120, stream=True)
    resp.raise_for_status()

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    size_kb = dest.stat().st_size // 1024
    log.info("excel_downloaded", filename=filename, size_kb=size_kb)
    return str(dest)

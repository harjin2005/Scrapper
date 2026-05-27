from __future__ import annotations
import asyncio
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright
from scraper.logger import get_logger

log = get_logger("excel_downloader")

_BASE_URL = "https://www.mctotx.org"

DELINQUENT_ROLL_PATTERN = re.compile(
    r"Delinquent\s+Tax\s+Roll\s*[-–]\s*Detail\s+as\s+of\s+([\w\s,]+\d{4})",
    re.IGNORECASE,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


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
        ctx = await browser.new_context(user_agent=_UA)
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


async def download_excel(download_url: str, as_of_date: str, downloads_dir: str) -> str:
    """Download Excel file via Playwright (handles CMS redirects), return local path."""
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

    # Use Playwright so browser handles CMS redirects and session cookies
    for attempt in range(3):
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    accept_downloads=True,
                    user_agent=_UA,
                )
                page = await ctx.new_page()
                try:
                    async with page.expect_download(timeout=180000) as dl_info:
                        await page.goto(download_url, wait_until="commit", timeout=30000)
                    dl = await dl_info.value
                    await dl.save_as(str(dest))
                finally:
                    await browser.close()
            size_kb = dest.stat().st_size // 1024
            log.info("excel_downloaded", filename=filename, size_kb=size_kb)
            return str(dest)
        except Exception as exc:
            if attempt < 2:
                log.warning("excel_download_retry", attempt=attempt + 1, error=str(exc))
                await asyncio.sleep(5)
            else:
                log.error("excel_download_failed", url=download_url, error=str(exc))
                raise

    raise RuntimeError(f"download failed after 3 attempts: {download_url}")

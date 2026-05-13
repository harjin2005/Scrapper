from __future__ import annotations
import asyncio
from datetime import date
from pathlib import Path
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.logger import get_logger

log = get_logger("clerk_scraper")


class ClerkScraper:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.downloads_dir = config.downloads_dir

    def _build_date_range(self, run_date: date) -> tuple[str, str]:
        from_date = date(run_date.year, run_date.month, 1)
        return from_date.strftime("%m/%d/%Y"), run_date.strftime("%m/%d/%Y")

    def _get_dated_download_path(self, run_date: date) -> str:
        folder = Path(self.downloads_dir) / run_date.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def _build_pdf_filename(self, instrument_no: str) -> str:
        return f"{instrument_no}_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"

    async def run(self, run_date: Optional[date] = None) -> list[tuple[str, str]]:
        """Returns list of (instrument_no, local_pdf_path) tuples."""
        run_date = run_date or date.today()
        from_date, to_date = self._build_date_range(run_date)
        download_dir = self._get_dated_download_path(run_date)
        log.info("clerk_search_start", from_date=from_date, to_date=to_date)

        results: list[tuple[str, str]] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.config.headless)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            page.set_default_timeout(self.config.request_timeout_ms)

            try:
                await self._navigate_and_search(page, from_date, to_date)
                results = await self._collect_all_pages(page, download_dir)
            except Exception as exc:
                log.error("clerk_scraper_failed", error=str(exc))
                raise
            finally:
                await browser.close()

        log.info("clerk_search_done", total_pdfs=len(results))
        return results

    async def _navigate_and_search(self, page: Page, from_date: str, to_date: str) -> None:
        await page.goto(self.config.clerk_portal_url)
        log.info("portal_loaded")

        doc_type = self.config.search_doc_type
        try:
            await page.select_option(
                "select[name*='DocType'], select[id*='DocType']",
                label=doc_type,
                timeout=5000,
            )
        except Exception:
            await page.fill("input[name*='DocType'], input[id*='DocType']", doc_type)

        date_from_selector = (
            "input[name*='DateFrom'], input[id*='DateFrom'], "
            "input[name*='FiledDateFrom'], input[id*='FiledDateFrom']"
        )
        date_to_selector = (
            "input[name*='DateTo'], input[id*='DateTo'], "
            "input[name*='FiledDateTo'], input[id*='FiledDateTo']"
        )
        await page.fill(date_from_selector, from_date)
        await page.fill(date_to_selector, to_date)

        await page.click("input[type='submit'], button[type='submit'], input[value*='Search']")
        await page.wait_for_load_state("networkidle")
        log.info("search_submitted", from_date=from_date, to_date=to_date)

    async def _collect_all_pages(self, page: Page, download_dir: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        page_num = 1
        while True:
            log.info("processing_results_page", page_num=page_num)
            page_results = await self._download_pdfs_on_page(page, download_dir)
            results.extend(page_results)

            next_btn = page.locator(
                "a:has-text('Next'), input[value='Next'], a[id*='Next'], a[aria-label*='next']"
            )
            if await next_btn.count() > 0:
                await next_btn.first.click()
                await page.wait_for_load_state("networkidle")
                page_num += 1
            else:
                break

        return results

    async def _download_pdfs_on_page(self, page: Page, download_dir: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        links = page.locator("table tr td a[href*='InstrumentNo'], table tr td a[href*='instrument']")
        count = await links.count()

        for i in range(count):
            link = links.nth(i)
            instrument_no = (await link.inner_text()).strip()
            if not instrument_no:
                continue
            try:
                local_path = await self._download_single_pdf(page, link, instrument_no, download_dir)
                if local_path:
                    results.append((instrument_no, local_path))
                    log.info("pdf_downloaded", instrument_no=instrument_no)
            except Exception as exc:
                log.error("pdf_download_failed", instrument_no=instrument_no, error=str(exc))

        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _download_single_pdf(
        self, page: Page, link, instrument_no: str, download_dir: str
    ) -> Optional[str]:
        filename = self._build_pdf_filename(instrument_no)
        dest_path = str(Path(download_dir) / filename)

        if Path(dest_path).exists():
            log.info("pdf_already_exists", instrument_no=instrument_no)
            return dest_path

        async with page.expect_download() as dl_info:
            await link.click()
        download = await dl_info.value
        await download.save_as(dest_path)
        return dest_path

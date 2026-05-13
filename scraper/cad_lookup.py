from __future__ import annotations
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import CADData
from scraper.logger import get_logger

log = get_logger("cad_lookup")


class CADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, grantor: Optional[str]) -> CADData:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    result = await self._search_by_address(page, address)
                    if result.account_number:
                        return result
                    if grantor:
                        result = await self._search_by_owner(page, grantor)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("cad_lookup_failed", address=address, error=str(exc))
            return CADData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_by_address(self, page: Page, address: str) -> CADData:
        await page.goto(self.config.cad_url)
        await page.fill(
            "input[placeholder*='ddress'], input[name*='address'], input[id*='address']",
            address,
        )
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_cad_data(page)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _search_by_owner(self, page: Page, owner: str) -> CADData:
        await page.goto(self.config.cad_url)
        await page.fill(
            "input[placeholder*='wner'], input[name*='owner'], input[id*='owner']",
            owner,
        )
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_cad_data(page)

    async def _extract_cad_data(self, page: Page) -> CADData:
        first_result = page.locator(
            "table tr:nth-child(2) td a, .property-result a, .search-result a"
        )
        if await first_result.count() > 0:
            await first_result.first.click()
            await page.wait_for_load_state("networkidle")

        account_number = await self._get_text(
            page,
            "[data-label*='Account'], td:has-text('Account') + td, .account-number",
        )
        appraised_value = await self._get_text(
            page,
            "[data-label*='Appraised'], [data-label*='Market'], td:has-text('Market Value') + td",
        )
        property_status = await self._get_text(
            page,
            "[data-label*='Status'], td:has-text('Status') + td",
        )
        log.info(
            "cad_data_extracted",
            account_number=account_number,
            appraised_value=appraised_value,
        )
        return CADData(
            account_number=account_number,
            appraised_value=appraised_value,
            property_status=property_status,
        )

    async def _get_text(self, page: Page, selector: str) -> Optional[str]:
        try:
            el = page.locator(selector).first
            if await el.count() > 0:
                text = (await el.inner_text()).strip()
                return text if text else None
        except Exception:
            pass
        return None

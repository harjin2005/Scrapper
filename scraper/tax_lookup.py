from __future__ import annotations
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import TaxData
from scraper.logger import get_logger

log = get_logger("tax_lookup")


class TaxLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, account_number: Optional[str]) -> TaxData:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    if account_number:
                        result = await self._search_by_account(page, account_number)
                        if result.taxes_due != "0":
                            return result
                    return await self._search_by_address(page, address)
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("tax_lookup_failed", address=address, error=str(exc))
            return TaxData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_by_address(self, page: Page, address: str) -> TaxData:
        await page.goto(self.config.tax_url)
        await page.fill(
            "input[placeholder*='ddress'], input[name*='address'], input[id*='address']",
            address,
        )
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_tax_data(page)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _search_by_account(self, page: Page, account_number: str) -> TaxData:
        await page.goto(self.config.tax_url)
        await page.fill(
            "input[placeholder*='ccount'], input[name*='account'], input[id*='account']",
            account_number,
        )
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")
        return await self._extract_tax_data(page)

    async def _extract_tax_data(self, page: Page) -> TaxData:
        first_result = page.locator("table tr:nth-child(2) td a, .property-result a")
        if await first_result.count() > 0:
            await first_result.first.click()
            await page.wait_for_load_state("networkidle")

        no_taxes = page.locator("text=no delinquent, text=current, text=no taxes due")
        if await no_taxes.count() > 0:
            log.info("tax_current", no_delinquent=True)
            return TaxData(taxes_due="Current", years_delinquent=0)

        taxes_text = await self._get_text(
            page,
            "[data-label*='Total'], td:has-text('Total Due') + td, .total-due, .amount-due",
        )
        years = 0
        if taxes_text:
            year_cells = page.locator("td.year, [data-label*='Year'], .delinquent-year")
            years = await year_cells.count()

        taxes_due = self._parse_amount(taxes_text) if taxes_text else "0"
        log.info("tax_data_extracted", taxes_due=taxes_due, years_delinquent=years)
        return TaxData(taxes_due=taxes_due, years_delinquent=years)

    def _parse_amount(self, text: str) -> str:
        m = re.search(r"\$?([\d,]+(?:\.\d{2})?)", text.replace(",", ""))
        if m:
            return m.group(1)
        return text.strip()

    async def _get_text(self, page: Page, selector: str) -> Optional[str]:
        try:
            el = page.locator(selector).first
            if await el.count() > 0:
                text = (await el.inner_text()).strip()
                return text if text else None
        except Exception:
            pass
        return None

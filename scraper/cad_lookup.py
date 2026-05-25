from __future__ import annotations
import re
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
        if not address:
            return CADData()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    result = await self._search(page, address)
                    if not result.account_number and grantor:
                        result = await self._search(page, grantor)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("cad_lookup_failed", address=address, error=str(exc))
            return CADData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search(self, page: Page, query: str) -> CADData:
        # Navigate with domcontentloaded to avoid JS-heavy networkidle timeout
        await page.goto(self.config.cad_url, wait_until="domcontentloaded")

        # Wait for React to render the search input
        try:
            await page.wait_for_selector("#searchInput", timeout=20000)
        except Exception:
            log.warning("cad_search_input_not_found")
            return CADData()

        await page.fill("#searchInput", query)
        await page.keyboard.press("Enter")

        # Wait for AG Grid rows (data rows, not header)
        try:
            await page.wait_for_selector(".ag-row:not(.ag-row-loading)", timeout=15000)
        except Exception:
            log.info("cad_no_results", query=query)
            return CADData()

        # Extract account number from first grid row
        # AG Grid cells have col-id attributes
        account_number = await self._get_cell_text(page, "pAccountID")
        if not account_number:
            # Try reading from the first row's visible text
            account_number = await self._get_cell_text(page, "pid")

        # Get the property pid for detail page navigation
        pid = await self._get_cell_text(page, "pid")

        appraised_value = None
        property_status = None

        if pid:
            detail_data = await self._get_detail(page, pid)
            appraised_value = detail_data.get("appraised_value")
            property_status = detail_data.get("property_status")

        log.info("cad_data_extracted", query=query, account_number=account_number, appraised_value=appraised_value)
        return CADData(
            account_number=account_number,
            appraised_value=appraised_value,
            property_status=property_status,
        )

    async def _get_cell_text(self, page: Page, col_id: str) -> Optional[str]:
        """Extract text from the first AG Grid row's cell with given col-id."""
        try:
            cell = page.locator(f'.ag-row:not(.ag-row-loading) [col-id="{col_id}"]').first
            if await cell.count() > 0:
                text = (await cell.inner_text()).strip()
                return text if text else None
        except Exception:
            pass
        return None

    async def _get_detail(self, page: Page, pid: str) -> dict:
        """Navigate to property detail page and extract appraised value and status."""
        import asyncio
        result: dict = {}
        try:
            # Try direct detail URL first (ProdigyCAD pattern)
            detail_url = self.config.cad_url.removesuffix("/property-search") + f"/property-detail/{pid}"
            current_url = page.url
            try:
                await page.goto(detail_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
            except Exception:
                # Fallback: click the first grid row
                await page.goto(current_url, wait_until="domcontentloaded")
                first_row = page.locator('.ag-row:not(.ag-row-loading)').first
                if await first_row.count() == 0:
                    return result
                await first_row.click()
                await asyncio.sleep(2)

            # Try to extract from detail page / panel
            body_text = await page.evaluate("() => document.body.innerText")

            # Market value / appraised value
            for pattern in [
                r"Market Value[:\s]+\$([\d,]+)",
                r"Appraised Value[:\s]+\$([\d,]+)",
                r"Total Value[:\s]+\$([\d,]+)",
                r"\$([\d,]+)\s*(?:Market|Appraised)",
            ]:
                m = re.search(pattern, body_text, re.IGNORECASE)
                if m:
                    result["appraised_value"] = m.group(1).strip()
                    break

            # Property status
            for pattern in [
                r"(?:Exemption|Status)[:\s]+([A-Z][A-Za-z\s]+?)(?:\n|$)",
                r"Property Status[:\s]+([^\n]+)",
            ]:
                m = re.search(pattern, body_text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    if val:
                        result["property_status"] = val
                        break
        except Exception as exc:
            log.warning("cad_detail_failed", error=str(exc))

        return result

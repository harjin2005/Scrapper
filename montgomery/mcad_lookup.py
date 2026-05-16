from __future__ import annotations
import asyncio
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from montgomery.config import Config
from montgomery.models import CADData
from scraper.logger import get_logger

log = get_logger("mcad_lookup")

# mcad-tx.org uses a React/AG-Grid interface similar to travis.prodigycad.com
_BASE = "https://mcad-tx.org"
_SEARCH_URL = _BASE + "/property-search"

# Property detail URL pattern: /property-detail/{pid}
_DETAIL_PATH = "/property-detail/"


class MCADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, account_number: str) -> CADData:
        """Primary search: by account number. Returns CADData."""
        if not account_number:
            return CADData()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    return await self._search(page, account_number)
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("mcad_lookup_failed", account=account_number, error=str(exc))
            return CADData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search(self, page: Page, account_number: str) -> CADData:
        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Try to find the search input (AG Grid / React portals vary)
        search_input = None
        for selector in ["#searchInput", "input[placeholder*='search' i]", "input[type='search']", "input[type='text']"]:
            try:
                await page.wait_for_selector(selector, timeout=8000)
                search_input = selector
                break
            except Exception:
                continue

        if not search_input:
            log.warning("mcad_search_input_not_found", account=account_number)
            return CADData()

        await page.fill(search_input, account_number)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        # Wait for AG Grid row
        try:
            await page.wait_for_selector(".ag-row:not(.ag-row-loading)", timeout=15000)
        except Exception:
            log.info("mcad_no_results", account=account_number)
            return CADData()

        # Try to get property ID for detail navigation
        pid = await self._get_cell_text(page, "pid")
        if not pid:
            pid = await self._get_cell_text(page, "pAccountID")

        # Extract what we can from the grid row
        owner = await self._get_cell_text(page, "owner") or await self._get_cell_text(page, "ownerName")
        address = await self._get_cell_text(page, "situs") or await self._get_cell_text(page, "address")

        cad = CADData(mailing_address=address)

        if pid:
            detail = await self._get_detail(page, pid)
            cad.property_type = detail.get("property_type")
            cad.property_type_code = detail.get("property_type_code")
            cad.appraised_value = detail.get("appraised_value")
            cad.lot_size = detail.get("lot_size")
            cad.legal_description = detail.get("legal_description")
            if detail.get("mailing_address"):
                cad.mailing_address = detail["mailing_address"]

        log.info("mcad_extracted", account=account_number, has_value=bool(cad.appraised_value))
        return cad

    async def _get_cell_text(self, page: Page, col_id: str) -> Optional[str]:
        try:
            cell = page.locator(f'.ag-row:not(.ag-row-loading) [col-id="{col_id}"]').first
            if await cell.count() > 0:
                text = (await cell.inner_text()).strip()
                return text if text else None
        except Exception:
            pass
        return None

    async def _get_detail(self, page: Page, pid: str) -> dict:
        result: dict = {}
        try:
            detail_url = _BASE + _DETAIL_PATH + pid
            await page.goto(detail_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            body = await page.evaluate("() => document.body.innerText")

            # Appraised / Market value
            for pattern in [
                r"Appraised Value[:\s]+\$([\d,]+)",
                r"Market Value[:\s]+\$([\d,]+)",
                r"Total Appraised[:\s]+\$([\d,]+)",
                r"\$([\d,]+)\s*(?:Appraised|Market)",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["appraised_value"] = m.group(1).strip()
                    break

            # Property use / type code
            for pattern in [
                r"Use Code[:\s]+([A-Z0-9]+)",
                r"Property Use[:\s]+([^\n]+)",
                r"State Code[:\s]+([A-Z0-9]+)",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["property_type_code"] = m.group(1).strip()
                    break

            # Property type description
            for pattern in [
                r"Property Type[:\s]+([^\n]+)",
                r"Class[:\s]+([^\n]{3,50})",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    if val and len(val) < 60:
                        result["property_type"] = val
                        break

            # Lot size / acreage
            for pattern in [
                r"Acres[:\s]+([\d,.]+)",
                r"Lot Size[:\s]+([\d,.\s]+(?:sq\s*ft|acres?)?)",
                r"Area[:\s]+([\d,.\s]+(?:sq\s*ft|acres?)?)",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["lot_size"] = m.group(1).strip()
                    break

            # Legal description
            m = re.search(r"Legal Description[:\s]+([^\n]{5,120})", body, re.IGNORECASE)
            if m:
                result["legal_description"] = m.group(1).strip()

            # Mailing address (from detail page)
            m = re.search(r"Mailing Address[:\s]+([^\n]{5,120})", body, re.IGNORECASE)
            if m:
                result["mailing_address"] = m.group(1).strip()

        except Exception as exc:
            log.warning("mcad_detail_failed", pid=pid, error=str(exc))

        return result

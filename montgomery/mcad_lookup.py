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
                # Use shorter timeout for MCAD — fail fast if site unreachable
                page.set_default_timeout(15000)
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

        # Extract from grid row using confirmed col-ids from mcad-tx.org
        pid = await self._get_cell_text(page, "pid")
        owner = await self._get_cell_text(page, "displayName")
        street = await self._get_cell_text(page, "streetPrimary")
        city = await self._get_cell_text(page, "city")
        prop_type = await self._get_cell_text(page, "propType")
        address = f"{street} {city}".strip() if street else city

        cad = CADData(mailing_address=address, property_type=prop_type)

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

            # mcad-tx.org (MUI/React) renders label then value on next line (no colon)
            # Pattern: "Label\nValue" OR "Label: Value" OR "Label Value"

            # Appraised / Market value
            for pattern in [
                r"(?:Appraised|Market|Total Appraised)\s+Value[:\s]*\n?\$?([\d,]+)",
                r"Appraised Value[:\s]+\$?([\d,]+)",
                r"Market Value[:\s]+\$?([\d,]+)",
                r"\$\s*([\d,]+)\s*\n?\s*(?:Appraised|Market)",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["appraised_value"] = m.group(1).replace(",", "").strip()
                    break

            # Property use / state code
            for pattern in [
                r"(?:Use Code|State Code)[:\s]*\n?([A-Z0-9]{1,10})\b",
                r"(?:Use Code|State Code)[:\s]+([A-Z0-9]+)",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["property_type_code"] = m.group(1).strip()
                    break

            # Property type description
            for pattern in [
                r"Property (?:Type|Class|Use)[:\s]*\n?([A-Za-z][^\n]{2,50})",
                r"(?:Residential|Commercial|Agricultural|Industrial|Land)\b",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    val = (m.group(1) if m.lastindex else m.group(0)).strip()
                    if val and len(val) < 60:
                        result["property_type"] = val
                        break

            # Lot size / acreage
            for pattern in [
                r"(?:Acres|Lot Size|Land Area)[:\s]*\n?([\d,.]+\s*(?:acres?|sq\.?\s*ft\.?)?)",
                r"([\d,.]+)\s*acres?",
                r"([\d,.]+)\s*sq\.?\s*ft\.?",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["lot_size"] = m.group(1).strip()
                    break

            # Legal description
            for pattern in [
                r"Legal Description[:\s]*\n?([^\n]{5,150})",
                r"Legal[:\s]*\n?([A-Z0-9][^\n]{5,150})",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["legal_description"] = m.group(1).strip()
                    break

            # Mailing address
            for pattern in [
                r"Mailing Address[:\s]*\n?([^\n]{5,120})",
                r"Mail[:\s]*\n?([0-9][^\n]{5,120})",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    result["mailing_address"] = m.group(1).strip()
                    break

        except Exception as exc:
            log.warning("mcad_detail_failed", pid=pid, error=str(exc))

        return result

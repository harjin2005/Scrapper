from __future__ import annotations
import asyncio
import re
from typing import Optional
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


def _owner_matches(expected: str, found: str) -> bool:
    """
    Return True if at least one significant word (>2 chars) from the expected owner
    appears in the found owner name. Handles name order differences and partial matches.
    """
    if not expected or not found:
        return True  # can't validate → assume OK
    expected_words = {w for w in expected.upper().split() if len(w) > 2}
    found_words = {w for w in found.upper().split() if len(w) > 2}
    return bool(expected_words & found_words)


class MCADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, account_number: str, expected_owner: str = "") -> CADData:
        """Primary search: by account number. Returns CADData.
        expected_owner: owner name from Excel — used to validate the MCAD result
        is actually the right property (MCAD may return a different property for
        accounts not registered there).
        """
        if not account_number:
            return CADData()
        for attempt in range(self.config.retry_attempts):
            try:
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=self.config.headless)
                    page = await browser.new_page()
                    page.set_default_timeout(15000)
                    try:
                        return await self._search(page, account_number, expected_owner)
                    finally:
                        await browser.close()
            except Exception as exc:
                if attempt < self.config.retry_attempts - 1:
                    log.warning("mcad_lookup_retry", account=account_number, attempt=attempt + 1, error=str(exc))
                    await asyncio.sleep(3)
                else:
                    log.error("mcad_lookup_failed", account=account_number, error=str(exc))
        return CADData()

    async def _search(self, page: Page, account_number: str, expected_owner: str = "") -> CADData:
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
        prop_type_code = await self._get_cell_text(page, "propType")
        address = " ".join(x for x in [street, city] if x).strip() or None

        # Validate that the grid result is actually the property we're looking for.
        # MCAD sometimes returns a different property for accounts not registered there.
        if owner and expected_owner and not _owner_matches(expected_owner, owner):
            log.info(
                "mcad_owner_mismatch_skipping",
                account=account_number,
                expected=expected_owner,
                found=owner,
            )
            return CADData()

        # Map single-letter code to full description
        _TYPE_MAP = {
            "R": "Residential", "C": "Commercial", "A": "Agricultural",
            "I": "Industrial", "M": "Manufactured Home", "U": "Utility",
            "X": "Exempt", "B": "Business Personal",
        }
        prop_type = _TYPE_MAP.get((prop_type_code or "").upper(), prop_type_code)

        cad = CADData(
            mailing_address=address,
            property_type=prop_type,
            property_type_code=prop_type_code,
        )

        if pid:
            detail = await self._get_detail(page, pid)
            # Keep grid prop_type (already mapped correctly); only take code from detail
            if detail.get("property_type_code"):
                cad.property_type_code = detail["property_type_code"]
            cad.appraised_value = detail.get("appraised_value")
            cad.lot_size = detail.get("lot_size")
            cad.legal_description = detail.get("legal_description")
            if detail.get("mailing_address"):
                cad.mailing_address = detail["mailing_address"]
            if detail.get("owner_name"):
                cad.owner_contact = detail["owner_name"]

        log.info("mcad_extracted", account=account_number,
                 has_value=bool(cad.appraised_value),
                 prop_type=cad.property_type,
                 prop_type_code=cad.property_type_code)
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

            # Wait until React API calls finish — values render as plain numbers (no $)
            try:
                await page.wait_for_function(
                    "() => document.body.innerText.includes('Net Appraised') && "
                    "!document.body.innerText.includes('Loading owner')",
                    timeout=20000,
                )
            except Exception:
                await asyncio.sleep(10)  # fallback

            body = await page.evaluate("() => document.body.innerText")

            # mcad-tx.org renders: "Label:\n\nValue\n\n" (label + blank line + value)
            # Values are plain numbers — NO dollar sign (e.g. "437,200" not "$437,200")

            # Appraised value — "Appraised\n\n437,200"
            m = re.search(r"\bAppraised\s*\n+\s*([\d,]+)", body, re.IGNORECASE)
            if m:
                result["appraised_value"] = m.group(1).replace(",", "").strip()

            # State code — "State Code:\n\nA1"
            m = re.search(r"State Code:\s*\n+\s*([A-Z][A-Z0-9]{0,4})\b", body)
            if m:
                result["property_type_code"] = m.group(1).strip()

            # Lot size — from Land table: "G2  Site Value  0.2410  10,500.00  ..."
            m = re.search(r"Site Value\s+([\d.]+)", body)
            if not m:
                m = re.search(r"([\d.]+)\s+[\d,]+\s+[\d,]+\s+0\s*$", body, re.MULTILINE)
            if m:
                result["lot_size"] = f"{m.group(1)} acres"

            # Legal description — "Legal Description:\n\nOAK RIDGE NORTH..."
            m = re.search(r"Legal Description:\s*\n+\s*([^\n]{5,150})", body)
            if m:
                result["legal_description"] = m.group(1).strip()

            # Mailing address — "Mailing Address:\n\n406 HEATHER LN CONROE TX USA 77385"
            m = re.search(r"Mailing Address:\s*\n+\s*([^\n]{10,120})", body)
            if m:
                result["mailing_address"] = m.group(1).strip()

            # Owner name from detail page (more current than grid — deed transfers update it)
            m = re.search(r"\bName:\s*\n+\s*([^\n]{3,80})", body)
            if m:
                result["owner_name"] = m.group(1).strip()

        except Exception as exc:
            log.warning("mcad_detail_failed", pid=pid, error=str(exc))

        return result

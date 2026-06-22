from __future__ import annotations
import asyncio
import re
from typing import Optional
from playwright.async_api import async_playwright, Page
from montgomery.config import Config
from montgomery.models import CADData
from scraper.logger import get_logger

log = get_logger("mcad_lookup")

_BASE = "https://mcad-tx.org"
_SEARCH_URL = _BASE + "/property-search"

_TYPE_MAP = {
    "R": "Residential", "C": "Commercial", "A": "Agricultural",
    "I": "Industrial", "M": "Manufactured Home", "U": "Utility",
    "X": "Exempt", "B": "Business Personal",
}


def _owner_matches(expected: str, found: str) -> bool:
    if not expected or not found:
        return True
    expected_words = {w for w in expected.upper().split() if len(w) > 2}
    found_words = {w for w in found.upper().split() if len(w) > 2}
    return bool(expected_words & found_words)


def _mailing_from_api(rec: dict) -> Optional[str]:
    parts = [
        rec.get("addrDeliveryLine", ""),
        rec.get("addrCity", ""),
        rec.get("addrState", ""),
        rec.get("addrZip", ""),
    ]
    return ", ".join(x for x in parts if x) or None


def _lot_size_from_api(rec: dict) -> Optional[str]:
    for field in ("legalAcreage", "effectiveSizeAcres"):
        raw = rec.get(field)
        try:
            val = float(raw or 0)
            if val > 0:
                return f"{val:.4f} acres"
        except (TypeError, ValueError):
            pass
    return None


class MCADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, account_number: str, expected_owner: str = "") -> CADData:
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
        # Intercept the TrueProdigy search API response — the search page fires a POST
        # to /public/property/search that returns the current-year record as JSON.
        # This is more reliable than scraping the detail page (whose values section
        # never renders in headless mode due to a lazy React API call).
        api_record: dict = {}

        async def _on_response(response):
            if "trueprodigyapi" in response.url and "property/search" in response.url:
                try:
                    data = await response.json()
                    results = data.get("results", [])
                    if results:
                        api_record.update(results[0])
                except Exception:
                    pass

        page.on("response", _on_response)

        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

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

        # Wait for both grid row AND API response
        try:
            await page.wait_for_selector(".ag-row:not(.ag-row-loading)", timeout=15000)
        except Exception:
            log.info("mcad_no_results", account=account_number)
            return CADData()

        await asyncio.sleep(3)  # ensure API response is captured

        if not api_record:
            log.warning("mcad_api_response_not_captured", account=account_number)
            return CADData()

        owner = api_record.get("displayName", "")
        if owner and expected_owner and not _owner_matches(expected_owner, owner):
            log.info(
                "mcad_owner_mismatch_skipping",
                account=account_number,
                expected=expected_owner,
                found=owner,
            )
            return CADData()

        prop_type_code = api_record.get("propType", "") or ""
        prop_type = _TYPE_MAP.get(prop_type_code.upper(), prop_type_code) or None

        # appraisedValue from API is the current-year Net Appraised value (no $ sign)
        raw_value = api_record.get("appraisedValue")
        appraised_value = str(int(raw_value)) if raw_value else None

        # fullSitus includes street, city, state, zip: "406 HEATHER LN, CONROE, TX, 77385"
        situs_address = api_record.get("fullSitus") or None

        mailing_address = _mailing_from_api(api_record)
        lot_size = _lot_size_from_api(api_record)
        legal_description = api_record.get("legalDescription") or None
        owner_contact = owner or None

        cad = CADData(
            property_type=prop_type,
            property_type_code=prop_type_code or None,
            appraised_value=appraised_value,
            situs_address=situs_address,
            mailing_address=mailing_address,
            lot_size=lot_size,
            legal_description=legal_description,
            owner_contact=owner_contact,
        )

        log.info(
            "mcad_extracted",
            account=account_number,
            has_value=bool(cad.appraised_value),
            appraised=cad.appraised_value,
            situs=cad.situs_address,
            prop_type=cad.property_type,
            prop_type_code=cad.property_type_code,
        )
        return cad

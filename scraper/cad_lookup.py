from __future__ import annotations
import asyncio
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from scraper.config import Config
from scraper.models import CADData
from scraper.logger import get_logger

log = get_logger("cad_lookup")

_SEARCH_URL = "https://travis.prodigycad.com/property-search"
_DETAIL_URL = "https://travis.prodigycad.com/property-detail/{pid}/2026"
_API_SEARCH = "searchfulltext"
_API_DEEDS = "/deeds"


class CADLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, grantor: Optional[str]) -> CADData:
        query = address.strip() if address and address.strip() else ""
        if not query and not grantor:
            return CADData()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    result = await self._search(page, query) if query else CADData()
                    if not result.uid and grantor:
                        result = await self._search(page, grantor)
                    if result.pid and not result.date_bought_by_owner:
                        result.date_bought_by_owner = await self._get_deed_date(page, result.pid)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("cad_lookup_failed", address=address, error=str(exc))
            return CADData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search(self, page: Page, query: str) -> CADData:
        captured: dict = {}

        async def _on_response(response):
            if _API_SEARCH in response.url:
                try:
                    if "json" in response.headers.get("content-type", ""):
                        captured["data"] = await response.json()
                except Exception:
                    pass

        page.on("response", _on_response)

        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("#searchInput", timeout=20_000)
        except Exception:
            log.warning("cad_search_input_not_found")
            page.remove_listener("response", _on_response)
            return CADData()

        await page.fill("#searchInput", query)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)

        page.remove_listener("response", _on_response)

        raw = captured.get("data", {})
        results = raw.get("results", [])
        if not results:
            log.info("cad_no_results", query=query)
            return CADData()

        rec = results[0] if isinstance(results, list) else results
        return _parse_cad_result(rec)

    async def _get_deed_date(self, page: Page, pid: str) -> Optional[str]:
        captured: dict = {}

        async def _on_response(response):
            if _API_DEEDS in response.url and str(pid) in response.url:
                try:
                    if "json" in response.headers.get("content-type", ""):
                        captured["data"] = await response.json()
                except Exception:
                    pass

        page.on("response", _on_response)
        detail_url = _DETAIL_URL.format(pid=pid)
        try:
            await page.goto(detail_url, wait_until="domcontentloaded")
            await asyncio.sleep(4)
        except Exception as exc:
            log.warning("cad_detail_nav_failed", pid=pid, error=str(exc))
        finally:
            page.remove_listener("response", _on_response)

        deeds = captured.get("data", {}).get("results", [])
        if deeds and isinstance(deeds, list):
            deed_dt = deeds[0].get("deedDt", "")
            if deed_dt:
                return deed_dt[:10]  # "2021-06-04 00:00:00" -> "2021-06-04"
        return None


def _parse_cad_result(rec: dict) -> CADData:
    uid_raw = rec.get("taxOfficeRef") or rec.get("refID2") or ""
    uid = uid_raw.lstrip("0") if uid_raw else None

    appraised = rec.get("appraisedValue")
    appraised_str = str(int(appraised)) if appraised is not None else None

    city = rec.get("city") or _parse_city_from_situs(rec.get("fullSitus", ""))

    return CADData(
        uid=uid or None,
        uid_raw=uid_raw or None,
        pid=str(rec.get("pid")) if rec.get("pid") else None,
        owner_name=rec.get("name") or None,
        owner_secondary=rec.get("nameSecondary") or None,
        property_street=rec.get("streetPrimary") or None,
        property_city=city or None,
        property_state=rec.get("state") or None,
        property_zip=rec.get("zip") or None,
        mailing_street=rec.get("addrDeliveryLine") or None,
        mailing_city=rec.get("addrCity") or None,
        mailing_state=rec.get("addrState") or None,
        mailing_zip=rec.get("addrZip") or None,
        appraised_value=appraised_str,
        property_type_code=rec.get("propType") or None,
        acreage=rec.get("legalAcreage") or None,
        legal_description=rec.get("legalDescription") or None,
        property_status=rec.get("active") or None,
        date_bought_by_owner=None,  # filled by _get_deed_date after search
    )


def _parse_city_from_situs(situs: str) -> Optional[str]:
    """Parse city from fullSitus like '360 NUECES ST, AUSTIN, TX, 78701'."""
    parts = [p.strip() for p in situs.split(",")]
    if len(parts) >= 3:
        candidate = parts[1]
        if len(candidate) > 3 and not candidate.isdigit():
            return candidate
    return None

from __future__ import annotations
import asyncio
from playwright.async_api import async_playwright
from scraper.config import Config
from scraper.logger import get_logger

log = get_logger("mls_lookup")

_MLS_SITES = ["zillow", "redfin", "realtor"]


class MlsLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def check(self, address: str) -> str:
        if not address or not address.strip():
            return "No"
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    query = f"{address} zillow OR redfin OR realtor"
                    bing_url = "https://www.bing.com/search?q=" + query.replace(" ", "+")
                    await page.goto(bing_url, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    body = await page.evaluate("() => document.body.innerText")
                    body_lower = body.lower()
                    listed = any(site in body_lower for site in _MLS_SITES)
                    result = "Yes" if listed else "No"
                    log.info("mls_check", address=address, result=result)
                    return result
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("mls_check_failed", address=address, error=str(exc))
            return "No"

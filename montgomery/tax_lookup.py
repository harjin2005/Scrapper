from __future__ import annotations
import asyncio
import re
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page
from montgomery.config import Config
from montgomery.models import TaxData
from scraper.logger import get_logger

log = get_logger("tax_lookup_montgomery")

# Montgomery County Tax Office — ACTweb JSP portal
_BASE = "https://actweb.acttax.com"
_PATH_PREFIX = "/act_webdev/montgomery/"
_SEARCH_URL = _BASE + _PATH_PREFIX + "index.jsp"

# Form field selectors (JSP portal, static HTML)
_SEL_ACCOUNT_INPUT = "input[name='accountNumber']"
_SEL_SEARCH_BTN = "input[type='submit'], button[type='submit']"
# ACTweb showlist links: href="showdetail.jsp?can=..." (relative, no leading slash)
_SEL_RESULT_LINK = "a[href*='showdetail'], a[href*='detail.jsp'], table a[href]"
_SEL_TAX_ROWS = "table tr"


class TaxLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, account_number: str) -> TaxData:
        if not account_number:
            return TaxData()
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
            log.error("tax_lookup_failed", account=account_number, error=str(exc))
            return TaxData()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search(self, page: Page, account_number: str) -> TaxData:
        log.info("tax_search", account=account_number, url=_SEARCH_URL)
        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Try account number input
        input_sel = None
        for sel in [_SEL_ACCOUNT_INPUT, "input[name='ownerName']", "input[type='text']"]:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                input_sel = sel
                break
            except Exception:
                continue

        if not input_sel:
            log.warning("tax_search_input_not_found", account=account_number)
            return TaxData()

        await page.fill(input_sel, account_number)
        await asyncio.sleep(0.3)

        # Submit form
        try:
            await page.click(_SEL_SEARCH_BTN)
        except Exception:
            await page.keyboard.press("Enter")

        await asyncio.sleep(3)

        current_url = page.url
        log.info("tax_post_search_url", account=account_number, url=current_url)

        # Navigate from showlist to detail page
        if "showlist" in current_url or "index" in current_url:
            try:
                await page.wait_for_selector(_SEL_RESULT_LINK, timeout=8000)
                links = page.locator(_SEL_RESULT_LINK)
                count = await links.count()
                log.info("tax_result_links_found", count=count, account=account_number)
                if count > 0:
                    href = await links.first.get_attribute("href") or ""
                    # Build correct absolute URL — ACTweb hrefs are relative to the JSP path
                    if href.startswith("http"):
                        detail_url = href
                    elif href.startswith("/"):
                        detail_url = _BASE + href
                    else:
                        detail_url = _BASE + _PATH_PREFIX + href
                    log.info("tax_navigating_detail", url=detail_url)
                    await page.goto(detail_url, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
            except Exception as exc:
                log.warning("tax_detail_nav_failed", account=account_number, error=str(exc))

        log.info("tax_detail_url", account=account_number, url=page.url)
        return await self._extract_detail(page)

    async def _extract_detail(self, page: Page) -> TaxData:
        body = await page.evaluate("() => document.body.innerText")

        if not body or len(body) < 50:
            log.warning("tax_empty_detail_page", url=page.url)
            return TaxData()

        result = TaxData()

        # Total amount due
        for pattern in [
            r"Total\s+(?:Amount\s+)?Due[:\s]+\$?([\d,]+\.?\d*)",
            r"Grand\s+Total[:\s]+\$?([\d,]+\.?\d*)",
            r"Balance\s+Due[:\s]+\$?([\d,]+\.?\d*)",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                result.total_due = m.group(1).replace(",", "").strip()
                break

        # Initial delinquency year — look for delinquent year entries in tax table
        year_pattern = re.compile(r"\b(20\d{2}|19\d{2})\b")
        delinquent_years: list[int] = []

        try:
            rows = page.locator(_SEL_TAX_ROWS)
            row_count = await rows.count()
            for i in range(1, row_count):
                row = rows.nth(i)
                cells = row.locator("td")
                cell_count = await cells.count()
                if cell_count < 2:
                    continue
                year_cell = (await cells.nth(0).inner_text()).strip()
                total_cell = (await cells.nth(cell_count - 1).inner_text()).strip()
                year_m = year_pattern.match(year_cell)
                amount = _parse_amount(total_cell)
                if year_m and amount > 0:
                    delinquent_years.append(int(year_m.group()))
        except Exception:
            # Fallback: extract years from body text near dollar amounts
            for m in re.finditer(r"\b(20\d{2}|19\d{2})\b.*?\$([\d,]+\.?\d*)", body):
                amt = _parse_amount(m.group(2))
                if amt > 0:
                    delinquent_years.append(int(m.group(1)))

        if delinquent_years:
            result.initial_delinquency_year = str(min(delinquent_years))
            result.years_behind = str(len(set(delinquent_years)))

        # Last payment date
        for pattern in [
            r"Last\s+Payment\s+Date[:\s]+([\d/\-]+)",
            r"Date\s+of\s+Last\s+Payment[:\s]+([\d/\-]+)",
            r"Paid\s+(?:in\s+Full\s+)?(?:on|through)[:\s]+([\d/\-]+)",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                result.last_payment_date = m.group(1).strip()
                break

        # Cause / lawsuit number
        for pattern in [
            r"Cause\s+(?:Number|No)[.:\s]+([\w\-]+)",
            r"Lawsuit\s+(?:Number|No)[.:\s]+([\w\-]+)",
            r"Suit\s+(?:Number|No)[.:\s]+([\w\-]+)",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                result.cause_number = m.group(1).strip()
                break

        # Cause date
        m = re.search(r"(?:Cause|Suit|Lawsuit)\s+Date[:\s]+([\d/\-]+)", body, re.IGNORECASE)
        if m:
            result.cause_date = m.group(1).strip()

        # Fallback: if table extraction missed total_due, scan body text
        if not result.total_due and body:
            for pattern in [
                r"Total\s+(?:Amount\s+)?Due[:\s]*\$?([\d,]+\.?\d*)",
                r"Grand\s+Total[:\s]*\$?([\d,]+\.?\d*)",
                r"Balance\s+Due[:\s]*\$?([\d,]+\.?\d*)",
                r"Total\s+Delinquency[:\s]*\$?([\d,]+\.?\d*)",
                r"\$\s*([\d,]+\.\d{2})\s",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    val = m.group(1).replace(",", "").strip()
                    if float(val) > 0:
                        result.total_due = val
                        break

        log.info(
            "tax_extracted",
            account_url=page.url,
            total_due=result.total_due,
            initial_year=result.initial_delinquency_year,
            years_behind=result.years_behind,
        )
        return result


def _parse_amount(text: str) -> float:
    cleaned = re.sub(r"[$,\s]", "", text)
    m = re.search(r"[\d]+(?:\.\d+)?", cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return 0.0

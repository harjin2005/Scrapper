from __future__ import annotations
import asyncio
import re
from typing import Optional
from playwright.async_api import async_playwright, Page
from montgomery.config import Config
from montgomery.models import TaxData
from scraper.logger import get_logger

log = get_logger("tax_lookup_montgomery")

# Montgomery County Tax Office — ACTweb JSP portal
_BASE = "https://actweb.acttax.com"
_PATH_PREFIX = "/act_webdev/montgomery/"
_SEARCH_URL = _BASE + _PATH_PREFIX + "index.jsp"

# Form field selectors (JSP portal)
# ACTweb uses radio button "searchby" to choose search type; value=4 = Account Search
# Default radio (value=3) is Name Search — submitting an account number to it returns 0 results
_SEL_ACCOUNT_RADIO = "input[name='searchby'][value='4']"
_SEL_CAD_RADIO = "input[name='searchby'][value='5']"   # CAD Reference Search fallback
_SEL_CRITERIA_INPUT = "input[name='criteria']"
_SEL_SEARCH_BTN = "input[type='submit'], button[type='submit']"
_SEL_RESULT_LINK = "a[href*='showdetail'], a[href*='detail.jsp']"
_NO_RESULTS_PATTERNS = ["no account", "no results", "no records", "not found", "0 account"]
_SEL_TAX_ROWS = "table tr"


class TaxLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, account_number: str, cad_ref: str | None = None) -> TaxData:
        if not account_number:
            return TaxData()
        for attempt in range(self.config.retry_attempts):
            try:
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=self.config.headless)
                    page = await browser.new_page()
                    page.set_default_timeout(self.config.request_timeout_ms)
                    try:
                        return await self._search(page, account_number, cad_ref=cad_ref)
                    finally:
                        await browser.close()
            except Exception as exc:
                if attempt < self.config.retry_attempts - 1:
                    log.warning("tax_lookup_retry", account=account_number, attempt=attempt + 1, error=str(exc))
                    await asyncio.sleep(5)
                else:
                    log.error("tax_lookup_failed", account=account_number, error=str(exc))
        return TaxData()

    async def _search(self, page: Page, account_number: str, cad_ref: str | None = None) -> TaxData:
        # ACTweb uses short account number (no leading zeros) with radio value=4 (Account Search)
        can_short = account_number.lstrip('0') or account_number
        log.info("tax_search", account=account_number, url=_SEARCH_URL)
        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Select "Account Search" radio (value=4) — default is Name Search (value=3)
        # Radio inputs may be styled/hidden; use JS click to bypass visibility checks
        try:
            await page.wait_for_selector(_SEL_ACCOUNT_RADIO, state="attached", timeout=8000)
            await page.evaluate("document.querySelector(\"input[name='searchby'][value='4']\").click()")
            log.info("tax_radio_selected", account=account_number)
        except Exception as exc:
            log.warning("tax_radio_not_found", account=account_number, error=str(exc))
            return TaxData()

        # Fill search criteria
        try:
            await page.wait_for_selector(_SEL_CRITERIA_INPUT, timeout=5000)
        except Exception:
            log.warning("tax_criteria_input_not_found", account=account_number)
            return TaxData()

        await page.fill(_SEL_CRITERIA_INPUT, can_short)
        await asyncio.sleep(0.3)
        try:
            await page.click(_SEL_SEARCH_BTN)
        except Exception:
            await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        current_url = page.url
        log.info("tax_post_search_url", account=account_number, url=current_url)

        # Navigate from showlist to detail page (only if direct URL didn't land on detail)
        if "showlist" in current_url or "index" in current_url:
            try:
                body_text = (await page.evaluate("() => document.body.innerText")).lower()
                # Detect no-results page early — don't try to navigate
                if any(p in body_text for p in _NO_RESULTS_PATTERNS):
                    # Account Search returned nothing — try CAD Reference Search with APRDISTACC
                    if cad_ref:
                        log.info("tax_cad_ref_fallback", account=account_number, cad_ref=cad_ref)
                        await page.goto(_SEARCH_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        try:
                            await page.evaluate("document.querySelector(\"input[name='searchby'][value='5']\").click()")
                            await page.fill(_SEL_CRITERIA_INPUT, cad_ref)
                            try:
                                await page.click(_SEL_SEARCH_BTN)
                            except Exception:
                                await page.keyboard.press("Enter")
                            await asyncio.sleep(3)
                            body_text2 = (await page.evaluate("() => document.body.innerText")).lower()
                            if any(p in body_text2 for p in _NO_RESULTS_PATTERNS):
                                log.info("tax_no_results", account=account_number)
                                return TaxData()
                        except Exception as exc:
                            log.warning("tax_cad_ref_search_failed", account=account_number, error=str(exc))
                            return TaxData()
                    else:
                        log.info("tax_no_results", account=account_number)
                        return TaxData()

                await page.wait_for_selector(_SEL_RESULT_LINK, timeout=8000)
                links = page.locator(_SEL_RESULT_LINK)
                count = await links.count()
                log.info("tax_result_links_found", count=count, account=account_number)
                if count > 0:
                    href = await links.first.get_attribute("href") or ""
                    # Build correct absolute URL — ACTweb hrefs are relative to JSP path
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
        result = await self._extract_detail(page)

        # Navigate to Tax Information and Receipts to get last payment date
        try:
            receipt_link = page.locator("a[href*='showreceipt'], a[href*='receipt']").first
            if await receipt_link.count() > 0:
                href = await receipt_link.get_attribute("href") or ""
                if href.startswith("http"):
                    receipt_url = href
                elif href.startswith("/"):
                    receipt_url = _BASE + href
                else:
                    receipt_url = _BASE + _PATH_PREFIX + href
                log.info("tax_navigating_receipts", url=receipt_url)
                await page.goto(receipt_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                last_paid = await self._extract_last_payment(page)
                if last_paid:
                    result.last_payment_date = last_paid
                    log.info("tax_last_payment_found", date=last_paid, account=account_number)
        except Exception as exc:
            log.warning("tax_receipt_nav_failed", account=account_number, error=str(exc))

        return result

    async def _extract_detail(self, page: Page) -> TaxData:
        body = await page.evaluate("() => document.body.innerText")

        if not body or len(body) < 50:
            log.warning("tax_empty_detail_page", url=page.url)
            return TaxData()

        result = TaxData()

        # Total amount due — ACTweb shows "Total Due" or "Grand Total" or "Balance Due"
        for pattern in [
            r"Total\s+(?:Amount\s+)?Due[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Grand\s+Total[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Balance\s+Due[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Total\s+Delinquency[:\s]*\$?\s*([\d,]+\.?\d*)",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                val = m.group(1).replace(",", "").strip()
                if _parse_amount(val) > 0:
                    result.total_due = val
                    break

        # Property address (situs) — "Situs: 2170 BROWN RD CONROE TX 77378"
        for pattern in [
            r"Situs[:\s]+([^\n]{10,80})",
            r"Property\s+Address[:\s]+([^\n]{10,80})",
            r"Site\s+Address[:\s]+([^\n]{10,80})",
            r"Location[:\s]+([^\n]{10,80})",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                addr = m.group(1).strip()
                # Filter out generic text
                if addr and not re.match(r'^(type|code|owner|name)', addr, re.IGNORECASE):
                    result.property_address = addr
                    break

        # Gross/appraised value from Tax website — fallback when CAD not available
        for pattern in [
            r"Appraised\s+Value[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Gross\s+Value[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"Market\s+Value[:\s]*\$?\s*([\d,]+\.?\d*)",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                val = m.group(1).replace(",", "").strip()
                if _parse_amount(val) > 0:
                    result.appraised_value = val
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
            for m in re.finditer(r"\b(20\d{2}|19\d{2})\b.*?\$([\d,]+\.?\d*)", body):
                amt = _parse_amount(m.group(2))
                if amt > 0:
                    delinquent_years.append(int(m.group(1)))

        if delinquent_years:
            result.initial_delinquency_year = str(min(delinquent_years))
            result.years_behind = str(len(set(delinquent_years)))

        # Last payment date — also try from main detail page body
        for pattern in [
            r"Last\s+Payment\s+Date[:\s]+([\w\s,/\-]+\d{4})",
            r"Date\s+of\s+Last\s+Payment[:\s]+([\w\s,/\-]+\d{4})",
            r"Paid\s+(?:in\s+Full\s+)?(?:on|through)[:\s]+([\w\s,/\-]+\d{4})",
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                result.last_payment_date = m.group(0).strip() if m.lastindex is None else m.group(1).strip()
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

        log.info(
            "tax_extracted",
            account_url=page.url,
            total_due=result.total_due,
            initial_year=result.initial_delinquency_year,
            years_behind=result.years_behind,
        )
        return result

    async def _extract_last_payment(self, page: Page) -> Optional[str]:
        """Extract most recent payment date from the Tax Information and Receipts page."""
        try:
            body = await page.evaluate("() => document.body.innerText")
            if not body:
                return None

            # Find all dates that look like payment dates
            # ACTweb receipt page shows dates like "01/21/2022" or "January 21, 2022"
            dates = re.findall(
                r'\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b'
                r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}',
                body,
                re.IGNORECASE,
            )
            if dates:
                # Return the first (most recent) date on the receipt page
                return dates[0].strip()
        except Exception as exc:
            log.warning("tax_receipt_extract_failed", error=str(exc))
        return None


def _parse_amount(text: str) -> float:
    cleaned = re.sub(r"[$,\s]", "", text)
    m = re.search(r"[\d]+(?:\.\d+)?", cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return 0.0

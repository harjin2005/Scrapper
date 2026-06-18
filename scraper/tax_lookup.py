from __future__ import annotations

import asyncio
import datetime
import re
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page

from scraper.config import Config
from scraper.models import TaxData
from scraper.logger import get_logger

log = get_logger("tax_lookup")

_GO2GOV_BASE    = "https://travis.go2gov.net"
_GO2GOV_SEARCH  = _GO2GOV_BASE + "/cart/responsive/search/displayQuickSearch.do?"
_DETAIL_URL     = _GO2GOV_BASE + "/showPropertyEntityDetail.do?account={uid}&year={year}"
_RECEIPTS_URL   = _GO2GOV_BASE + "/showPaymentReceipts.do?account={uid}"

_SEL_QSF_INPUT   = "#qsfInput"
_SEL_QSF_SUBMIT  = "#qsfButtonSearch"
_SEL_RESULT_LINK = "a[href*='showPropertyInfo.do']"
_SEL_TAX_ROWS    = "table tr"


class TaxLookup:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def lookup(self, address: str, uid_raw: Optional[str]) -> TaxData:
        """
        uid_raw: 14-digit account number with leading zero (from CAD taxOfficeRef/refID2).
        address: fallback if uid_raw not available.
        """
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.config.headless)
                page = await browser.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)
                try:
                    if uid_raw:
                        return await self._lookup_by_uid(page, uid_raw)
                    return await self._search_by_address(page, address)
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("tax_lookup_failed", address=address, error=str(exc))
            return TaxData()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _lookup_by_uid(self, page: Page, uid_raw: str) -> TaxData:
        year = datetime.date.today().year
        detail_url = _DETAIL_URL.format(uid=uid_raw, year=year)
        log.info("tax_uid_lookup", url=detail_url)
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        result = await self._extract_from_detail_page(page)

        receipts_url = _RECEIPTS_URL.format(uid=uid_raw)
        try:
            await page.goto(receipts_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            result.last_payment_date = await self._extract_last_payment_date(page)
        except Exception as exc:
            log.warning("tax_receipts_failed", uid=uid_raw, error=str(exc))

        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_by_address(self, page: Page, address: str) -> TaxData:
        log.info("tax_address_search", address=address)
        await page.goto(_GO2GOV_SEARCH, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        await page.wait_for_selector(_SEL_QSF_INPUT, timeout=15_000)
        await page.fill(_SEL_QSF_INPUT, address)
        await asyncio.sleep(0.5)
        await page.click(_SEL_QSF_SUBMIT)
        await asyncio.sleep(4)

        try:
            await page.wait_for_selector(_SEL_RESULT_LINK, timeout=10_000)
        except Exception:
            log.warning("tax_no_results", address=address, url=page.url)
            return TaxData()

        best_link = await self._best_result_link(page, address)
        if not best_link:
            log.warning("tax_no_matching_result", address=address)
            return TaxData()

        href = await best_link.get_attribute("href") or ""
        detail_url = href if href.startswith("http") else f"{_GO2GOV_BASE}{href}"
        log.info("tax_navigating_to_detail", url=detail_url)
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        return await self._extract_from_detail_page(page)

    async def _best_result_link(self, page: Page, address: str):
        links = page.locator(_SEL_RESULT_LINK)
        count = await links.count()
        if count == 0:
            return None
        if count == 1:
            return links.first

        address_upper = address.upper().strip()
        best_el, best_score = None, -1

        for i in range(count):
            el = links.nth(i)
            try:
                td = el.locator("xpath=ancestor::td[1]")
                td_text = (await td.inner_text()).upper()
                score = _address_match_score(address_upper, td_text)
                if score > best_score:
                    best_score = score
                    best_el = el
            except Exception:
                continue

        return best_el if best_el is not None else links.first

    async def _extract_from_detail_page(self, page: Page) -> TaxData:
        try:
            await page.wait_for_selector(_SEL_TAX_ROWS, timeout=10_000)
        except Exception:
            log.warning("tax_no_table", url=page.url)
            return TaxData()

        rows = page.locator(_SEL_TAX_ROWS)
        total_rows = await rows.count()
        data_rows = total_rows - 1

        if data_rows <= 0:
            log.info("tax_no_data_rows", url=page.url)
            return TaxData(taxes_due="Current", years_delinquent=0)

        grand_total = 0.0
        years_with_balance: list[str] = []

        for i in range(1, total_rows):
            row = rows.nth(i)
            cells = row.locator("td")
            cell_count = await cells.count()
            if cell_count == 0:
                continue

            year_text  = (await cells.nth(0).inner_text()).strip()
            total_text = (await cells.nth(cell_count - 1).inner_text()).strip()
            amount     = _parse_amount(total_text)

            if amount > 0:
                grand_total += amount
                years_with_balance.append(year_text)
            elif i == 1 and amount == 0:
                log.info("tax_current", url=page.url)
                return TaxData(taxes_due="Current", years_delinquent=0)

        years_delinquent = len(years_with_balance)
        taxes_due = f"{grand_total:.2f}" if grand_total > 0 else "Current"
        initial_year = min(years_with_balance) if years_with_balance else None

        log.info("tax_extracted", taxes_due=taxes_due, years_delinquent=years_delinquent)
        return TaxData(
            taxes_due=taxes_due,
            years_delinquent=years_delinquent,
            initial_delinquency_year=initial_year,
        )

    async def _extract_last_payment_date(self, page: Page) -> Optional[str]:
        """
        showPaymentReceipts.do table:
        Header row: Receipt | Tax Year | Payment Date | Payment Amount
        First data row (index 1) = most recent payment, column 2 = date
        """
        try:
            await page.wait_for_selector(_SEL_TAX_ROWS, timeout=8_000)
            rows = page.locator(_SEL_TAX_ROWS)
            count = await rows.count()
            if count < 2:
                return None
            first_data_row = rows.nth(1)
            cells = first_data_row.locator("td")
            cell_count = await cells.count()
            if cell_count >= 3:
                date_text = (await cells.nth(2).inner_text()).strip()
                return date_text if date_text else None
        except Exception as exc:
            log.warning("tax_receipts_parse_failed", error=str(exc))
        return None


def _parse_amount(text: str) -> float:
    cleaned = text.replace(",", "").replace("$", "").strip()
    m = re.search(r"[\d]+(?:\.\d+)?", cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return 0.0


def _address_match_score(query: str, candidate: str) -> int:
    q_tokens = set(re.split(r"\W+", query))
    c_tokens = set(re.split(r"\W+", candidate))
    q_tokens.discard("")
    c_tokens.discard("")
    return len(q_tokens & c_tokens)

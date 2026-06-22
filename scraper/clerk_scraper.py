from __future__ import annotations
import base64
import re
import random as _random
import shutil
import subprocess
import asyncio
from datetime import date
from pathlib import Path
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page, BrowserContext
from scraper.config import Config
from scraper.logger import get_logger
from scraper.models import ListingEntry

log = get_logger("clerk_scraper")

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_PROFILE = str(Path.home() / "AppData/Local/Google/Chrome/User Data")
TEMP_PROFILE = str(Path("config/chrome_scrape_profile").resolve())
CDP_PORT = 9223

HOME_URL = "https://www.tccsearch.org/"
SEARCH_URL = "https://www.tccsearch.org/RealEstate/SearchEntry.aspx"

# Checkbox index for "NOTICE OF SUBSTITUTE TRUSTEE SALE" in the doc type list
FORECLOSURE_CHECKBOX_ID = "cphNoMargin_f_dclDocType_72"
SEARCH_BTN_ID = "cphNoMargin_SearchButtons1_btnSearch"


class ClerkScraper:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.downloads_dir = config.downloads_dir

    def _build_date_range(self, run_date: date) -> tuple[str, str]:
        from_date = date(run_date.year, run_date.month, 1)
        return from_date.strftime("%m/%d/%Y"), run_date.strftime("%m/%d/%Y")

    def _get_dated_download_path(self, run_date: date) -> str:
        folder = Path(self.downloads_dir) / run_date.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def _build_pdf_filename(self, instrument_no: str) -> str:
        return f"{instrument_no}_NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE.pdf"

    def _copy_chrome_profile(self) -> None:
        temp = Path(TEMP_PROFILE)
        # If profile already exists, keep it — preserves Cloudflare clearance cookies
        if temp.exists():
            log.info("reusing_existing_chrome_profile")
            return
        temp.mkdir(parents=True, exist_ok=True)
        src = Path(CHROME_PROFILE) / "Default"
        dst = temp / "Default"
        if src.exists():
            log.info("copying_chrome_profile")
            shutil.copytree(str(src), str(dst), ignore=shutil.ignore_patterns(
                "Cache", "Code Cache", "GPUCache", "Service Worker",
                "CacheStorage", "VideoDecodeStats", "*.log", "*.tmp",
                "blob_storage", "databases",
            ))

    async def run(self, run_date: Optional[date] = None) -> list[ListingEntry]:
        run_date = run_date or date.today()
        from_date, to_date = self._build_date_range(run_date)
        download_dir = self._get_dated_download_path(run_date)
        log.info("clerk_search_start", from_date=from_date, to_date=to_date)

        self._copy_chrome_profile()
        proc = None
        proc = subprocess.Popen([
            CHROME_EXE,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={TEMP_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-minimized",
        ])
        # Wait for Chrome to start, retry connecting (localhost → 127.0.0.1 avoids IPv6 issue)
        await asyncio.sleep(5)

        results: list[tuple[str, str]] = []
        try:
            async with async_playwright() as pw:
                browser = None
                for attempt in range(6):
                    try:
                        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                        break
                    except Exception:
                        if attempt == 5:
                            raise RuntimeError(f"Chrome CDP not ready on 127.0.0.1:{CDP_PORT} after 6 attempts")
                        await asyncio.sleep(2)

                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                page.set_default_timeout(self.config.request_timeout_ms)

                try:
                    await self._check_cloudflare_health(page)
                    await self._navigate_and_search(page, from_date, to_date)
                    results = await self._collect_all_pages(page, download_dir, context)
                except Exception as exc:
                    log.error("clerk_scraper_failed", error=str(exc))
                    raise
                finally:
                    await browser.close()
        finally:
            if proc:
                proc.terminate()
            # Keep temp profile so Cloudflare clearance cookie survives between runs

        log.info("clerk_search_done", total_pdfs=len(results))
        return results

    async def _check_cloudflare_health(self, page: Page) -> None:
        """Early exit if Cloudflare blocks homepage — avoids 3h run before discovery."""
        for attempt in range(3):
            await page.goto(HOME_URL, wait_until="domcontentloaded")
            title = await page.title()
            if "Just a moment" not in title and "Cloudflare" not in title:
                log.info("cloudflare_health_ok", title=title)
                return
            log.warning("cloudflare_blocking_homepage", attempt=attempt + 1, title=title)
            await asyncio.sleep(10)
        raise RuntimeError(
            "Cloudflare is blocking tccsearch.org after 3 attempts. "
            "Open Chrome manually, pass the challenge, then re-run."
        )

    async def _wait_for_load(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            await asyncio.sleep(2)

    async def _wait_for_title(self, page: Page, not_contains: str, timeout_ms: int = 30000) -> str:
        elapsed = 0
        while elapsed < timeout_ms:
            try:
                title = await page.title()
                if not_contains not in title:
                    return title
            except Exception:
                pass
            await asyncio.sleep(1)
            elapsed += 1000
        raise RuntimeError(f"Timed out waiting for title to not contain '{not_contains}'")

    async def _navigate_and_search(self, page: Page, from_date: str, to_date: str) -> None:
        # Step 1: load home page, pass Cloudflare
        log.info("navigating_to_home")
        await page.goto(HOME_URL, wait_until="domcontentloaded")
        title = await self._wait_for_title(page, "Just a moment", timeout_ms=180000)
        log.info("cloudflare_cleared", title=title)

        # Step 2: click disclaimer accept link if present
        await self._wait_for_load(page)
        accept = page.locator("#cph1_lnkAccept")
        if await accept.count() > 0:
            log.info("clicking_disclaimer_accept")
            await accept.click()
            await asyncio.sleep(2)
            await self._wait_for_load(page)

        # Step 3: navigate to search form
        log.info("navigating_to_search_form")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded")
        await self._wait_for_load(page)
        try:
            title = await page.title()
            log.info("search_form_loaded", title=title)
        except Exception:
            pass

        await self._fill_and_submit_form(page, from_date, to_date)

    async def _fill_and_submit_form(self, page: Page, from_date: str, to_date: str) -> None:
        # Check the NOTICE OF SUBSTITUTE TRUSTEE SALE checkbox
        checkbox = page.locator(f"#{FORECLOSURE_CHECKBOX_ID}")
        if await checkbox.count() > 0:
            await checkbox.check()
            log.info("doc_type_checked")
        else:
            # Fallback: find by label text
            label = page.locator("label", has_text="NOTICE OF SUBSTITUTE TRUSTEE SALE")
            if await label.count() > 0:
                await label.click()
                log.info("doc_type_checked_via_label")
            else:
                log.warning("doc_type_checkbox_not_found")

        # Fill date pickers (Infragistics ElectricBlue date editors)
        date_inputs = page.locator("input.igte_ElectricBlueEditInContainer")
        count = await date_inputs.count()
        if count >= 2:
            # FROM date
            await date_inputs.nth(0).click(click_count=3)
            await date_inputs.nth(0).type(from_date)
            await date_inputs.nth(0).press("Tab")
            await asyncio.sleep(0.5)
            # TO date
            await date_inputs.nth(1).click(click_count=3)
            await date_inputs.nth(1).type(to_date)
            await date_inputs.nth(1).press("Tab")
            await asyncio.sleep(0.5)
            log.info("dates_filled", from_date=from_date, to_date=to_date)
        else:
            log.warning("date_inputs_not_found", count=count)

        # Click search — wait for the ASP.NET form post navigation to complete
        async with page.expect_navigation(wait_until="networkidle", timeout=60000):
            await page.evaluate(f"document.getElementById('{SEARCH_BTN_ID}').click()")
        log.info("search_submitted")

    async def _get_total_pages(self, page: Page) -> int:
        """Read the page-select dropdown to learn total page count."""
        try:
            count = await page.evaluate("""() => {
                const sel = document.getElementById('cphNoMargin_cphNoMargin_OptionsBar1_ItemList')
                          || document.getElementById('cphNoMargin_cphNoMargin_OptionsBar2_ItemList');
                if (!sel) return 1;
                return sel.options.length;
            }""")
            return int(count) if count and int(count) > 0 else 1
        except Exception:
            return 1

    async def _collect_all_pages(self, page: Page, download_dir: str, context: BrowserContext) -> list[tuple[str, str]]:
        results: list[ListingEntry] = []
        await asyncio.sleep(2)
        await self._wait_for_load(page)

        # Discover total pages from the dropdown on the results page
        total_pages = await self._get_total_pages(page)
        log.info("pagination_detected", total_pages=total_pages)

        # Page 1 is already loaded
        log.info("processing_results_page", page_num=1)
        results.extend(await self._download_pdfs_on_page(page, download_dir, context))

        # Navigate directly to SearchResults.aspx?pg=N for pages 2+
        base_url = "https://www.tccsearch.org/RealEstate/SearchResults.aspx"
        for page_num in range(2, total_pages + 1):
            url = f"{base_url}?pg={page_num}"
            log.info("processing_results_page", page_num=page_num, url=url)
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await self._wait_for_load(page)
                await asyncio.sleep(1)
                page_results = await self._download_pdfs_on_page(page, download_dir, context)
                if not page_results:
                    log.info("empty_page_stopping", page_num=page_num)
                    break
                results.extend(page_results)
            except Exception as exc:
                log.error("page_navigation_failed", page_num=page_num, error=str(exc))
                break

        return results

    async def _download_pdfs_on_page(self, page: Page, download_dir: str, context: BrowserContext) -> list[ListingEntry]:
        # Extract instrument #, global_id, and listing-level fields from each result row.
        # The Name column contains "[R] GRANTOR NAME (+)\n[E] MM/DD/YYYY (+)" —
        # [R] = registrant/grantor, [E] = sale/auction date from the listing grid.
        link_data: list[dict] = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="global_id"][href*="type=dtl"]');
            return Array.from(links).map(a => {
                const row = a.closest('tr');
                const cells = row ? Array.from(row.querySelectorAll('td')) : [];
                const instrIdx = cells.findIndex(td => td.contains(a));

                let dateFiled = '', grantor = '', saleDate = '', legalDesc = '';

                if (instrIdx >= 0) {
                    // Date Filed: cell immediately after instrument # cell
                    if (cells[instrIdx + 1]) {
                        dateFiled = cells[instrIdx + 1].innerText.trim();
                    }
                    // Name cell: contains "[R]" marker — search forward from instrument cell
                    for (let i = instrIdx + 1; i < cells.length; i++) {
                        const txt = cells[i].innerText || '';
                        if (txt.includes('[R]')) {
                            const rM = txt.match(/\\[R\\]\\s*([^\\n(]+)/);
                            if (rM) grantor = rM[1].trim();
                            const eM = txt.match(/\\[E\\]\\s*([\\d\\/]+)/);
                            if (eM) saleDate = eM[1].trim();
                            break;
                        }
                    }
                    // Legal description: last non-trivial cell before status ("Temp")
                    for (let i = cells.length - 1; i > instrIdx; i--) {
                        const txt = cells[i].innerText.trim();
                        if (txt && txt !== 'Temp' && !txt.includes('[R]') && !txt.includes('[E]')) {
                            legalDesc = txt;
                            break;
                        }
                    }
                }

                return {
                    text: a.innerText.trim(),
                    href: a.getAttribute('href') || '',
                    dateFiled,
                    grantor,
                    saleDate,
                    legalDesc
                };
            });
        }""")
        log.info("found_result_links", count=len(link_data))

        results: list[ListingEntry] = []
        for item in link_data:
            instrument_no = item["text"]
            href = item["href"]
            if not instrument_no or "global_id=" not in href:
                continue
            global_id = href.split("global_id=")[1].split("&")[0]
            try:
                local_path = await self._download_single_pdf(instrument_no, global_id, download_dir, context)
                if local_path:
                    entry = ListingEntry(
                        instrument_no=instrument_no,
                        local_path=local_path,
                        date_filed=item.get("dateFiled") or None,
                        grantor_listing=item.get("grantor") or None,
                        sale_date_listing=item.get("saleDate") or None,
                        legal_desc_listing=item.get("legalDesc") or None,
                        relevant_doc_link=f"https://www.tccsearch.org/RealEstate/DocumentDetail.aspx?global_id={global_id}",
                    )
                    results.append(entry)
                    log.info(
                        "pdf_downloaded",
                        instrument_no=instrument_no,
                        grantor_listing=entry.grantor_listing,
                        sale_date_listing=entry.sale_date_listing,
                    )
            except Exception as exc:
                log.error("pdf_download_failed", instrument_no=instrument_no, error=str(exc))

        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _download_single_pdf(
        self, instrument_no: str, global_id: str, download_dir: str, context: BrowserContext
    ) -> Optional[str]:
        filename = self._build_pdf_filename(instrument_no)
        dest_path = Path(download_dir) / filename

        if dest_path.exists():
            log.info("pdf_already_exists", instrument_no=instrument_no)
            return str(dest_path)

        # Step 1: load printHelper HTML page to get the server-generated r= value
        ph_html_url = (
            f"https://www.tccsearch.org/Controls/printHelper.aspx"
            f"?t=P&id={global_id}&rnd={_random.random()}"
        )
        html_page = await context.new_page()
        try:
            await html_page.goto(ph_html_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            html_src = await html_page.evaluate("() => document.documentElement.outerHTML")
        finally:
            await html_page.close()

        m = re.search(r"printHelper\.aspx\?r=([\d.]+)", html_src)
        if not m:
            raise RuntimeError(f"No r= in printHelper response for {global_id}")
        r_val = m.group(1)
        pdf_r_url = f"https://www.tccsearch.org/Controls/printHelper.aspx?r={r_val}"
        log.info("pdf_r_url_found", instrument_no=instrument_no, r_val=r_val)

        # Step 2: intercept the PDF response via CDP Fetch.enable before
        #         Chrome's PDF viewer can wrap it in extension HTML
        dl_page = await context.new_page()
        cdp = await context.new_cdp_session(dl_page)
        await cdp.send("Fetch.enable", {
            "patterns": [
                {"urlPattern": "**/Controls/printHelper.aspx?r=*", "requestStage": "Response"}
            ]
        })

        loop = asyncio.get_running_loop()
        pdf_future: asyncio.Future = loop.create_future()

        async def _on_paused(params: dict) -> None:
            req_id = params["requestId"]
            hdrs = {h["name"].lower(): h["value"] for h in params.get("responseHeaders", [])}
            ct = hdrs.get("content-type", "")
            if "pdf" in ct.lower():
                try:
                    res = await cdp.send("Fetch.getResponseBody", {"requestId": req_id})
                    body_data = res.get("body", "")
                    is_b64 = res.get("base64Encoded", False)
                    pdf_bytes = base64.b64decode(body_data) if is_b64 else body_data.encode("latin-1")
                    if not pdf_future.done():
                        pdf_future.set_result(pdf_bytes)
                except Exception as exc:
                    if not pdf_future.done():
                        pdf_future.set_exception(exc)
            try:
                await cdp.send("Fetch.continueRequest", {"requestId": req_id})
            except Exception:
                pass

        cdp.on("Fetch.requestPaused", lambda p: asyncio.ensure_future(_on_paused(p)))

        try:
            await dl_page.goto(pdf_r_url, wait_until="domcontentloaded")
            pdf_bytes = await asyncio.wait_for(pdf_future, timeout=60)
            dest_path.write_bytes(pdf_bytes)
            log.info("pdf_saved", instrument_no=instrument_no, bytes=len(pdf_bytes))
            return str(dest_path)
        except Exception as exc:
            log.error("pdf_fetch_failed", instrument_no=instrument_no, error=str(exc))
            raise
        finally:
            try:
                await cdp.detach()
            except Exception:
                pass
            await dl_page.close()

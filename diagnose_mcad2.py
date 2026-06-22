"""Diagnose MCAD detail page for account 130387 — why has_value=False."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(30000)

        print("Loading MCAD search...")
        await page.goto("https://mcad-tx.org/property-search", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        await page.fill("#searchInput", "130387")
        await page.keyboard.press("Enter")
        await asyncio.sleep(5)

        ag_rows = await page.locator(".ag-row").count()
        print(f"AG rows: {ag_rows}")

        # Read all col-ids
        for col in ["pid", "propType", "displayName", "streetPrimary", "city", "geoID", "refID1", "taxOfficeRef"]:
            try:
                cell = page.locator(f'.ag-row:not(.ag-row-loading) [col-id="{col}"]').first
                if await cell.count() > 0:
                    text = (await cell.inner_text()).strip()
                    print(f"  {col}: '{text}'")
            except:
                pass

        # Get pid
        pid_el = page.locator('.ag-row:not(.ag-row-loading) [col-id="pid"]').first
        pid = ""
        if await pid_el.count() > 0:
            pid = (await pid_el.inner_text()).strip()
        print(f"\nPID: '{pid}'")

        if pid:
            detail_url = f"https://mcad-tx.org/property-detail/{pid}"
            print(f"Navigating to detail: {detail_url}")
            await page.goto(detail_url, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            print(f"Detail URL: {page.url}")

            body = await page.evaluate("() => document.body.innerText")
            with open("mcad_detail.txt", "w", encoding="utf-8") as f:
                f.write(body)
            print(f"Detail text saved to mcad_detail.txt ({len(body)} chars)")
            print(f"\nFirst 2000 chars:\n{body[:2000]}")

            # Also save HTML
            html = await page.evaluate("() => document.body.innerHTML")
            with open("mcad_detail.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\nHTML saved to mcad_detail.html")

        await browser.close()

asyncio.run(main())

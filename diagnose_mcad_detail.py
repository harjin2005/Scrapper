"""Diagnose MCAD detail page structure for account 130387."""
import asyncio
import sys
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(60000)

        await page.goto("https://mcad-tx.org/property-search", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        await page.fill("#searchInput", "130387")
        await page.keyboard.press("Enter")
        await asyncio.sleep(5)

        # Read grid row col-ids
        ag_rows = await page.locator(".ag-row").count()
        print(f"AG rows: {ag_rows}")

        for col in ["pid", "propType", "displayName", "streetPrimary", "city", "geoID", "refID1", "taxOfficeRef", "seq"]:
            try:
                cell = page.locator(f'.ag-row:not(.ag-row-loading) [col-id="{col}"]').first
                if await cell.count() > 0:
                    text = (await cell.inner_text()).strip()
                    print(f"  col-id={col}: '{text}'")
                else:
                    print(f"  col-id={col}: (no element)")
            except Exception as e:
                print(f"  col-id={col}: ERROR {e}")

        # Get pid to navigate detail
        pid_cell = page.locator('.ag-row:not(.ag-row-loading) [col-id="pid"]').first
        pid = ""
        if await pid_cell.count() > 0:
            pid = (await pid_cell.inner_text()).strip()
        print(f"\nPID: '{pid}'")

        if pid:
            detail_url = f"https://mcad-tx.org/property-detail/{pid}"
            print(f"Navigating to: {detail_url}")
            await page.goto(detail_url, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            body = await page.evaluate("() => document.body.innerText")
            # Write to file to avoid encoding issues
            with open("mcad_detail_body.txt", "w", encoding="utf-8") as f:
                f.write(body)
            print("Detail body saved to mcad_detail_body.txt")
            print(f"First 1000 chars:\n{body[:1000]}")

        await browser.close()

asyncio.run(main())

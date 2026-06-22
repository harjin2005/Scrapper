"""Diagnose MCAD site structure."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    print("MCAD diagnostic")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(60000)

        await page.goto("https://mcad-tx.org/property-search", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        print(f"URL after load: {page.url}")

        # What inputs exist?
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(i => ({
                id: i.id, name: i.name, type: i.type,
                placeholder: i.placeholder, class: i.className.slice(0,60)
            }));
        }""")
        print(f"\nInputs on page:")
        for inp in inputs:
            print(f"  {inp}")

        # Find search input
        search_sel = None
        for sel in ["#searchInput", "input[placeholder*='search' i]", "input[type='search']", "input[type='text']"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    search_sel = sel
                    break
            except:
                continue
        print(f"\nSearch selector: {search_sel}")

        if search_sel:
            await page.fill(search_sel, "130387")
            await page.keyboard.press("Enter")
            await asyncio.sleep(5)
            print(f"URL after search: {page.url}")

        # AG Grid rows
        ag_rows = await page.locator(".ag-row").count()
        print(f"AG Grid .ag-row count: {ag_rows}")

        # All col-id attributes
        col_ids = await page.evaluate("""() => {
            return [...new Set(Array.from(document.querySelectorAll('[col-id]'))
                .map(el => el.getAttribute('col-id')))];
        }""")
        print(f"col-id values: {col_ids}")

        # Table structure
        tables = await page.locator("table").count()
        print(f"Tables: {tables}")

        # Print full body text
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\nBody text (first 2000):\n{body_text[:2000]}")

        # Print inner HTML snippet
        html = await page.evaluate("() => document.body.innerHTML")
        print(f"\nHTML (first 3000):\n{html[:3000]}")

        await browser.close()

asyncio.run(main())

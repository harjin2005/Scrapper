"""Diagnostic: print actual HTML from Tax + MCAD sites to see real structure."""
import asyncio
from playwright.async_api import async_playwright


async def diagnose_tax():
    print("\n" + "="*60)
    print("TAX OFFICE — showlist.jsp link structure")
    print("="*60)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(60000)
        await page.goto("https://actweb.acttax.com/act_webdev/montgomery/index.jsp", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Fill account number and submit
        try:
            await page.wait_for_selector("input[name='accountNumber']", timeout=8000)
            await page.fill("input[name='accountNumber']", "000000130387")
            await page.click("input[type='submit'], button[type='submit']")
            await asyncio.sleep(4)
        except Exception as e:
            print(f"Search failed: {e}")

        url = page.url
        print(f"Current URL: {url}")

        # Print all <a> tags
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                href: a.href,
                text: a.innerText.trim().slice(0, 60)
            }));
        }""")
        print(f"\nAll links on page ({len(links)}):")
        for l in links[:30]:
            print(f"  href={l['href']}  text={l['text']}")

        # Print first 3000 chars of body text
        body = await page.evaluate("() => document.body.innerHTML")
        print(f"\nHTML snippet (first 3000 chars):\n{body[:3000]}")
        await browser.close()


async def diagnose_mcad():
    print("\n" + "="*60)
    print("MCAD — search result structure")
    print("="*60)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(60000)
        await page.goto("https://mcad-tx.org/property-search", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Find and fill search input
        search_sel = None
        for sel in ["#searchInput", "input[placeholder*='search' i]", "input[type='search']", "input[type='text']"]:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                search_sel = sel
                break
            except:
                continue
        print(f"Search selector found: {search_sel}")

        if search_sel:
            await page.fill(search_sel, "130387")
            await page.keyboard.press("Enter")
            await asyncio.sleep(4)

        url = page.url
        print(f"Current URL: {url}")

        # Check for AG Grid
        ag_rows = await page.locator(".ag-row").count()
        print(f"AG Grid rows: {ag_rows}")

        # Check for any table rows
        table_rows = await page.locator("table tr").count()
        print(f"Table rows: {table_rows}")

        # Print all column headers / cell col-ids
        col_ids = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[col-id]')).map(el => el.getAttribute('col-id'));
        }""")
        print(f"col-id attributes found: {set(col_ids)}")

        body = await page.evaluate("() => document.body.innerHTML")
        print(f"\nHTML snippet (first 3000 chars):\n{body[:3000]}")
        await browser.close()


asyncio.run(diagnose_tax())
asyncio.run(diagnose_mcad())

"""Take screenshots of all 4 pages for account 130387."""
import asyncio
from playwright.async_api import async_playwright

CAN = "000000130387"
CAD = "130387"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        p = await b.new_page(viewport={"width": 1280, "height": 900})
        p.set_default_timeout(30000)

        # 1. ACTweb search → detail page (Total Tax Due)
        await p.goto("https://actweb.acttax.com/act_webdev/montgomery/index.jsp")
        await asyncio.sleep(2)
        await p.evaluate("document.querySelector(\"input[name='searchby'][value='5']\").click()")
        await p.fill("input[name='criteria']", CAD)
        await p.click("input[type='submit']")
        await asyncio.sleep(3)
        link = p.locator("a[href*='showdetail']").first
        href = await link.get_attribute("href")
        detail_url = "https://actweb.acttax.com/act_webdev/montgomery/" + href
        await p.goto(detail_url)
        await asyncio.sleep(3)
        await p.screenshot(path="/tmp/ss1_detail.png", full_page=True)
        print("ss1_detail.png done")

        # 2. Year breakdown page
        year_url = detail_url.replace("showdetail2.jsp", "reports/taxbyyear.jsp")
        await p.goto(year_url)
        await asyncio.sleep(2)
        await p.screenshot(path="/tmp/ss2_years.png", full_page=True)
        print("ss2_years.png done")

        # 3. Payment history page
        pay_url = detail_url.replace("showdetail2.jsp", "reports/paymentinfo.jsp")
        await p.goto(pay_url)
        await asyncio.sleep(2)
        await p.screenshot(path="/tmp/ss3_payments.png", full_page=True)
        print("ss3_payments.png done")

        # 4. MCAD property search
        await p.goto("https://mcad-tx.org/property-search")
        await asyncio.sleep(3)
        for sel in ["#searchInput", "input[placeholder*='search' i]", "input[type='search']", "input[type='text']"]:
            try:
                await p.wait_for_selector(sel, timeout=3000, state="visible")
                await p.fill(sel, CAD)
                break
            except Exception:
                continue
        await p.keyboard.press("Enter")
        await asyncio.sleep(3)
        await p.screenshot(path="/tmp/ss4_mcad_search.png", full_page=True)
        print("ss4_mcad_search.png done")

        # Click first result if visible
        try:
            result = p.locator("a[href*='property-detail'], tr[class*='row'] a, .result-row a").first
            if await result.count() > 0:
                await result.click()
                await asyncio.sleep(3)
                await p.screenshot(path="/tmp/ss5_mcad_detail.png", full_page=True)
                print("ss5_mcad_detail.png done")
        except Exception as exc:
            print("MCAD detail click failed:", exc)

        await b.close()

asyncio.run(main())

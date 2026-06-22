"""
Live investigation of Travis CAD and Travis Tax Assessor.
Captures API responses, page structure, and available fields.
"""
import asyncio
import json
from playwright.async_api import async_playwright

# Known test address from our sample PDF data
TEST_ADDRESS = "1234 Oak Street, Austin, TX 78701"
TEST_GRANTOR = "JOHN A. DOE"


async def investigate_travis_cad():
    print("\n" + "="*60)
    print("TRAVIS CAD INVESTIGATION")
    print("="*60)

    api_responses = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Intercept ALL network responses to find APIs
        async def on_response(response):
            url = response.url
            if any(x in url.lower() for x in ["api", "search", "property", "prodigy"]):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        api_responses.append({"url": url, "data": data})
                        print(f"[API HIT] {url}")
                except Exception:
                    pass

        page.on("response", on_response)

        print(f"Navigating to travis.prodigycad.com/property-search ...")
        await page.goto("https://travis.prodigycad.com/property-search", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Find search input
        for sel in ["#searchInput", "input[placeholder*='search' i]", "input[type='text']"]:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                await page.fill(sel, TEST_ADDRESS)
                await page.keyboard.press("Enter")
                print(f"Searched with selector: {sel}")
                break
            except Exception:
                continue

        await asyncio.sleep(5)

        print(f"\nAPI responses captured: {len(api_responses)}")
        for r in api_responses:
            print(f"\nURL: {r['url']}")
            data = r['data']
            if isinstance(data, dict):
                results = data.get("results", data.get("data", []))
                if results and isinstance(results, list) and len(results) > 0:
                    first = results[0]
                    print(f"FIRST RESULT KEYS: {list(first.keys()) if isinstance(first, dict) else type(first)}")
                    print(f"FIRST RESULT: {json.dumps(first, indent=2, default=str)[:2000]}")
                else:
                    print(f"DATA KEYS: {list(data.keys())}")
                    print(f"DATA SAMPLE: {json.dumps(data, indent=2, default=str)[:1000]}")

        # Also capture page text to see what's rendered
        try:
            body = await page.evaluate("() => document.body.innerText")
            print(f"\nPAGE TEXT SAMPLE (first 500 chars):\n{body[:500]}")
        except Exception as e:
            print(f"Page text error: {e}")

        await browser.close()


async def investigate_travis_tax():
    print("\n" + "="*60)
    print("TRAVIS TAX ASSESSOR INVESTIGATION")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        api_hits = []

        async def on_response(response):
            url = response.url
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    data = await response.json()
                    api_hits.append({"url": url, "data": data})
            except Exception:
                pass

        page.on("response", on_response)

        print("Navigating to go2gov tax search ...")
        go2gov_url = "https://travis.go2gov.net/cart/responsive/search/displayQuickSearch.do?"
        await page.goto(go2gov_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Fill search
        for sel in ["#qsfInput", "input[name*='criteria']", "input[type='text']"]:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                await page.fill(sel, TEST_ADDRESS)
                print(f"Filled input: {sel}")
                break
            except Exception:
                continue

        # Submit
        for sel in ["#qsfButtonSearch", "button[type='submit']", "input[type='submit']"]:
            try:
                await page.click(sel)
                print(f"Clicked: {sel}")
                break
            except Exception:
                continue

        await asyncio.sleep(4)

        body = await page.evaluate("() => document.body.innerText")
        print(f"\nSEARCH RESULTS PAGE (first 1000 chars):\n{body[:1000]}")
        print(f"\nCurrent URL: {page.url}")

        # Try clicking first result
        try:
            await page.wait_for_selector("a[href*='showPropertyInfo']", timeout=8000)
            links = await page.locator("a[href*='showPropertyInfo']").all()
            print(f"\nResult links found: {len(links)}")
            if links:
                href = await links[0].get_attribute("href")
                print(f"First link href: {href}")
                # Extract UID/account from href
                import re
                m = re.search(r'account=([^&]+)', href or "")
                if m:
                    print(f"ACCOUNT/UID FROM URL: {m.group(1)}")

                await links[0].click()
                await asyncio.sleep(3)

                detail_body = await page.evaluate("() => document.body.innerText")
                print(f"\nDETAIL PAGE (first 2000 chars):\n{detail_body[:2000]}")
        except Exception as e:
            print(f"No result links: {e}")

        if api_hits:
            print(f"\nAPI hits: {len(api_hits)}")
            for h in api_hits[:3]:
                print(f"URL: {h['url']}")

        await browser.close()


async def investigate_mls_options():
    print("\n" + "="*60)
    print("MLS CHECK OPTIONS")
    print("="*60)

    # Option A: Google search + check if zillow/redfin in results
    # We check if a simple Google search returns MLS listings
    TEST_PROP = "606 West Lynn Street Austin TX 78703"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        query = f"{TEST_PROP} site:zillow.com OR site:redfin.com OR site:realtor.com"
        google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        print(f"Google query: {query}")
        await page.goto(google_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        body = await page.evaluate("() => document.body.innerText")
        has_zillow = "zillow" in body.lower()
        has_redfin = "redfin" in body.lower()
        has_realtor = "realtor" in body.lower()
        print(f"Zillow found: {has_zillow}")
        print(f"Redfin found: {has_redfin}")
        print(f"Realtor found: {has_realtor}")
        print(f"MLS Listed (Option A): {'Yes' if any([has_zillow, has_redfin, has_realtor]) else 'No'}")
        print(f"\nPage sample:\n{body[:500]}")

        await browser.close()


async def main():
    await investigate_travis_cad()
    await investigate_travis_tax()
    await investigate_mls_options()

if __name__ == "__main__":
    asyncio.run(main())

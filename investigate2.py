"""
Deep investigation using the real example property: EMMICK RYAN / 360 Nueces ST 3301 Austin TX 78701
UID example: 1070028210000
CAD property detail: https://travis.prodigycad.com/property-detail/771190/2026
Tax URL: https://travis.go2gov.net/showPropertyEntityDetail.do?account=01070028210000&year=2025
"""
import asyncio
import json
from playwright.async_api import async_playwright

CAD_SEARCH_URL = "https://travis.prodigycad.com/property-search"
CAD_DETAIL_URL = "https://travis.prodigycad.com/property-detail/771190/2026"
TAX_SEARCH_URL = "https://travis.go2gov.net/cart/responsive/search/displayQuickSearch.do?"
TAX_DETAIL_URL = "https://travis.go2gov.net/showPropertyEntityDetail.do?account=01070028210000&year=2025"

TEST_ADDRESS = "360 Nueces ST 3301"
TEST_OWNER = "EMMICK RYAN"


async def investigate_cad_search():
    print("\n" + "="*60)
    print("TRAVIS CAD — SEARCH API RESPONSE FIELDS")
    print("="*60)

    api_responses = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(response):
            url = response.url
            if "trueprodigyapi" in url and any(x in url for x in ["search", "property", "detail"]):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        api_responses[url] = data
                except Exception:
                    pass

        page.on("response", on_response)

        await page.goto(CAD_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        try:
            await page.wait_for_selector("#searchInput", timeout=10000)
            await page.fill("#searchInput", TEST_ADDRESS)
            await page.keyboard.press("Enter")
            print(f"Searched: {TEST_ADDRESS}")
        except Exception as e:
            print(f"Search input error: {e}")

        await asyncio.sleep(5)

        for url, data in api_responses.items():
            if "property/search" in url or "propertySearch" in url.lower():
                print(f"\n[SEARCH API] {url}")
                results = data.get("results", [])
                if results and isinstance(results, list):
                    print(f"Total results: {len(results)}")
                    for i, r in enumerate(results[:3]):
                        print(f"\n--- Result {i+1} ---")
                        print(json.dumps(r, indent=2, default=str))
                else:
                    print(json.dumps(data, indent=2, default=str)[:2000])

        await browser.close()


async def investigate_cad_detail():
    print("\n" + "="*60)
    print("TRAVIS CAD — PROPERTY DETAIL PAGE API FIELDS")
    print("="*60)

    api_responses = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(response):
            url = response.url
            if "trueprodigyapi" in url:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        api_responses[url] = data
                        print(f"[API] {url}")
                except Exception:
                    pass

        page.on("response", on_response)

        print(f"Loading CAD detail: {CAD_DETAIL_URL}")
        await page.goto(CAD_DETAIL_URL, wait_until="domcontentloaded")
        await asyncio.sleep(6)

        for url, data in api_responses.items():
            print(f"\n{'='*40}")
            print(f"URL: {url}")
            if isinstance(data, dict):
                results = data.get("results", data)
                if isinstance(results, list) and results:
                    print(f"KEYS: {list(results[0].keys()) if isinstance(results[0], dict) else 'not dict'}")
                    print(json.dumps(results[0], indent=2, default=str)[:3000])
                elif isinstance(results, dict):
                    print(f"KEYS: {list(results.keys())}")
                    print(json.dumps(results, indent=2, default=str)[:3000])

        await browser.close()


async def investigate_tax_detail():
    print("\n" + "="*60)
    print("TRAVIS TAX ASSESSOR — DIRECT DETAIL PAGE")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        api_hits = {}
        async def on_response(response):
            url = response.url
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    data = await response.json()
                    api_hits[url] = data
            except Exception:
                pass

        page.on("response", on_response)

        print(f"Loading tax detail directly: {TAX_DETAIL_URL}")
        await page.goto(TAX_DETAIL_URL, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        body = await page.evaluate("() => document.body.innerText")
        print(f"\nFULL PAGE TEXT:\n{body[:4000]}")
        print(f"\nCurrent URL: {page.url}")

        if api_hits:
            print(f"\nAPI hits: {list(api_hits.keys())}")

        await browser.close()


async def investigate_tax_search_correct():
    print("\n" + "="*60)
    print("TRAVIS TAX ASSESSOR — SEARCH WITH CORRECT FORMAT")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(TAX_SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Try "360 Nueces" format (street number + street name)
        for query in ["360 Nueces", "Emmick Ryan", "1070028210000"]:
            print(f"\nTrying query: '{query}'")
            try:
                await page.fill("#qsfInput", "")
                await page.fill("#qsfInput", query)
                await page.click("#qsfButtonSearch")
                await asyncio.sleep(3)

                body = await page.evaluate("() => document.body.innerText")
                if "did not return" not in body and "no result" not in body.lower():
                    print(f"SUCCESS with '{query}'")
                    print(f"Results page:\n{body[:2000]}")

                    # Try to click first result
                    try:
                        links = await page.locator("a[href*='showPropertyInfo']").all()
                        print(f"Result links: {len(links)}")
                        if links:
                            for link in links[:3]:
                                href = await link.get_attribute("href")
                                text = await link.inner_text()
                                print(f"  Link: {text.strip()[:80]} -> {href}")
                    except Exception as e:
                        print(f"Link extract error: {e}")
                    break
                else:
                    print(f"No results for '{query}'")
                    # Go back to search
                    await page.goto(TAX_SEARCH_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"Error: {e}")

        await browser.close()


async def investigate_mls_bing():
    print("\n" + "="*60)
    print("MLS CHECK — BING SEARCH (avoids Google bot detection)")
    print("="*60)

    TEST_PROP = "360 Nueces ST 3301 Austin TX 78701"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Try Bing
        bing_url = f"https://www.bing.com/search?q={TEST_PROP.replace(' ', '+')}+zillow+OR+redfin+OR+realtor"
        print(f"Bing query: {bing_url}")
        await page.goto(bing_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        body = await page.evaluate("() => document.body.innerText")
        has_zillow = "zillow" in body.lower()
        has_redfin = "redfin" in body.lower()
        has_realtor = "realtor" in body.lower()
        print(f"Zillow in results: {has_zillow}")
        print(f"Redfin in results: {has_redfin}")
        print(f"Realtor in results: {has_realtor}")
        print(f"MLS Listed: {'Yes' if any([has_zillow, has_redfin, has_realtor]) else 'No'}")
        print(f"\nPage sample:\n{body[:800]}")

        # Also try Zillow directly
        print("\n--- Direct Zillow search ---")
        zillow_url = f"https://www.zillow.com/homes/{TEST_PROP.replace(' ', '-')}/"
        await page.goto(zillow_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        zillow_body = await page.evaluate("() => document.body.innerText")
        print(f"Zillow page sample:\n{zillow_body[:600]}")

        await browser.close()


async def main():
    await investigate_cad_search()
    await investigate_cad_detail()
    await investigate_tax_detail()
    await investigate_tax_search_correct()
    await investigate_mls_bing()

if __name__ == "__main__":
    asyncio.run(main())

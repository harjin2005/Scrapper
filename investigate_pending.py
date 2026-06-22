"""
Investigation of 3 pending data sources:
1. go2gov RECEIPTS tab -> last_payment_date
2. go2gov PRIOR BILL tab -> initial_delinquency_year
3. CAD /deeds endpoint -> date_bought_by_owner

Test property: EMMICK RYAN / UID 01070028210000 / pid 771190
"""
import asyncio
import json
from playwright.async_api import async_playwright

UID_14 = "01070028210000"
CAD_PID = "771190"
GO2GOV_BASE = "https://travis.go2gov.net"
CAD_BASE = "https://prod-container.trueprodigyapi.com"


async def investigate_go2gov_receipts():
    print("\n" + "="*60)
    print("GO2GOV — RECEIPTS TAB")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Start on detail page
        detail_url = f"{GO2GOV_BASE}/showPropertyEntityDetail.do?account={UID_14}&year=2025"
        print(f"Loading: {detail_url}")
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        body = await page.evaluate("() => document.body.innerText")
        print(f"\nDetail page (first 1500 chars):\n{body[:1500]}")

        # Find nav links
        nav_links = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a'));
            return links.map(a => ({text: a.innerText.trim(), href: a.href}))
                        .filter(l => l.text.length > 0);
        }""")
        print(f"\nAll nav links on detail page:")
        for l in nav_links:
            print(f"  '{l['text']}' -> {l['href']}")

        # Try to find RECEIPTS link
        receipts_link = None
        for l in nav_links:
            if "RECEIPT" in l["text"].upper() or "receipt" in l["href"].lower() or "payment" in l["href"].lower():
                receipts_link = l["href"]
                print(f"\nFound RECEIPTS: {receipts_link}")
                break

        if receipts_link:
            await page.goto(receipts_link, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            receipts_body = await page.evaluate("() => document.body.innerText")
            print(f"\nRECEIPTS PAGE:\n{receipts_body[:3000]}")

            receipts_html = await page.evaluate("() => document.body.innerHTML")
            print(f"\nRECEIPTS HTML (first 3000):\n{receipts_html[:3000]}")
        else:
            # Try common go2gov receipt URL patterns
            for url_suffix in [
                f"/showReceipts.do?account={UID_14}",
                f"/cart/responsive/showReceipts.do?account={UID_14}",
                f"/showPaymentHistory.do?account={UID_14}",
                f"/showPropertyEntityDetail.do?account={UID_14}&year=2025&selectedTab=receipts",
            ]:
                url = f"{GO2GOV_BASE}{url_suffix}"
                print(f"\nTrying: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    b = await page.evaluate("() => document.body.innerText")
                    if len(b) > 200 and "not found" not in b.lower():
                        print(f"SUCCESS:\n{b[:2000]}")
                        break
                    else:
                        print(f"Empty/not found")
                except Exception as e:
                    print(f"Error: {e}")

        await browser.close()


async def investigate_go2gov_prior_bill():
    print("\n" + "="*60)
    print("GO2GOV — PRIOR BILL TAB")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Try prior year detail
        for year in [2024, 2023, 2022]:
            url = f"{GO2GOV_BASE}/showPropertyEntityDetail.do?account={UID_14}&year={year}"
            print(f"\nTrying year {year}: {url}")
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            body = await page.evaluate("() => document.body.innerText")
            print(f"Body (500 chars):\n{body[:500]}")

            if "delinquent" in body.lower() or "past due" in body.lower() or "Delinquent" in body:
                print(">>> Found delinquency info!")
                break

        # Try PRIOR BILL specific URL patterns
        for url_suffix in [
            f"/showPriorBill.do?account={UID_14}",
            f"/showOriginalBill.do?account={UID_14}",
            f"/showPropertyEntityDetail.do?account={UID_14}&selectedTab=priorBill",
            f"/cart/responsive/showOriginalBill.do?account={UID_14}",
        ]:
            url = f"{GO2GOV_BASE}{url_suffix}"
            print(f"\nTrying: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                b = await page.evaluate("() => document.body.innerText")
                if len(b) > 200:
                    print(f"Got content:\n{b[:2000]}")
            except Exception as e:
                print(f"Error: {e}")

        await browser.close()


async def investigate_go2gov_full_page():
    """Get full HTML of main detail page to find tab links and payment history."""
    print("\n" + "="*60)
    print("GO2GOV — FULL DETAIL PAGE STRUCTURE")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Track all network requests
        requests_made = []
        async def on_request(request):
            requests_made.append(request.url)

        page.on("request", on_request)

        detail_url = f"{GO2GOV_BASE}/showPropertyEntityDetail.do?account={UID_14}&year=2025"
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Full HTML
        html = await page.evaluate("() => document.documentElement.outerHTML")
        print(f"\nFULL HTML (first 8000 chars):\n{html[:8000]}")

        print(f"\nAll network requests:")
        for r in requests_made:
            print(f"  {r}")

        await browser.close()


async def investigate_cad_deeds():
    print("\n" + "="*60)
    print("CAD — /deeds ENDPOINT")
    print("="*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        api_hits = {}
        async def on_response(response):
            url = response.url
            if "trueprodigyapi" in url:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        api_hits[url] = data
                        print(f"[API] {url}")
                except Exception:
                    pass

        page.on("response", on_response)

        # Navigate to CAD detail page — this triggers /deeds call
        detail_url = f"https://travis.prodigycad.com/property-detail/{CAD_PID}/2026"
        print(f"Loading: {detail_url}")
        await page.goto(detail_url, wait_until="domcontentloaded")
        await asyncio.sleep(6)

        for url, data in api_hits.items():
            print(f"\n{'='*40}")
            print(f"URL: {url}")
            print(f"Response:")
            print(json.dumps(data, indent=2, default=str)[:4000])

        # Also try hitting /deeds directly
        deeds_url = f"{CAD_BASE}/public/property/{CAD_PID}/deeds"
        print(f"\nDirect deeds URL: {deeds_url}")
        response = await page.request.get(deeds_url)
        try:
            deeds_data = await response.json()
            print(f"Direct deeds response:")
            print(json.dumps(deeds_data, indent=2, default=str)[:3000])
        except Exception as e:
            print(f"Direct deeds error: {e}")
            text = await response.text()
            print(f"Text: {text[:500]}")

        await browser.close()


async def main():
    await investigate_cad_deeds()
    await investigate_go2gov_full_page()
    await investigate_go2gov_receipts()
    await investigate_go2gov_prior_bill()


if __name__ == "__main__":
    asyncio.run(main())

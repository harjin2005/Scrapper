"""Wait for React to fully render MCAD detail page and capture values."""
import asyncio, re
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(30000)

        await page.goto("https://mcad-tx.org/property-detail/130387", wait_until="domcontentloaded")

        # Wait up to 20s for dollar amounts to appear
        print("Waiting for dollar values to render...")
        for i in range(20):
            await asyncio.sleep(1)
            body = await page.evaluate("() => document.body.innerText")
            dollars = re.findall(r'\$[\d,]+', body)
            print(f"  t={i+1}s: dollar amounts found: {dollars[:5]}")
            if dollars:
                print("Dollar values appeared!")
                break

        body = await page.evaluate("() => document.body.innerText")
        with open("mcad_detail_waited.txt", "w", encoding="utf-8") as f:
            f.write(body)
        print(f"\nFull body ({len(body)} chars) saved to mcad_detail_waited.txt")
        print(f"\nFirst 3000:\n{body[:3000]}")

        await browser.close()

asyncio.run(main())

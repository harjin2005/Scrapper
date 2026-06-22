"""Diagnose Montgomery Tax Office showlist + detail page."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(60000)

        print("Loading tax search page...")
        await page.goto("https://actweb.acttax.com/act_webdev/montgomery/index.jsp",
                        wait_until="domcontentloaded")
        await asyncio.sleep(3)
        print(f"URL: {page.url}")

        # Print all inputs
        inputs = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('input,select')).map(i=>({
                tag:i.tagName, name:i.name, type:i.type, id:i.id
            }))
        """)
        print(f"Inputs: {inputs}")

        # Fill account number
        try:
            await page.fill("input[name='accountNumber']", "000000130387")
            await page.click("input[type='submit']")
        except Exception as e:
            print(f"Fill/submit error: {e}")
            # Try any submit
            await page.keyboard.press("Enter")

        await asyncio.sleep(5)
        print(f"After search URL: {page.url}")

        # Print all links
        links = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('a')).map(a=>({
                href: a.getAttribute('href'), text: a.innerText.trim().slice(0,50)
            }))
        """)
        print(f"\nLinks on results page ({len(links)}):")
        for l in links[:20]:
            print(f"  {l}")

        # Save full HTML
        html = await page.evaluate("() => document.body.innerHTML")
        with open("tax_showlist.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nFull HTML saved to tax_showlist.html ({len(html)} chars)")

        # If showlist, try clicking first result
        if "showlist" in page.url or links:
            for l in links:
                href = l.get("href") or ""
                if "showdetail" in href or "detail" in href.lower():
                    full = href if href.startswith("http") else f"https://actweb.acttax.com{href}"
                    print(f"\nNavigating to detail: {full}")
                    await page.goto(full, wait_until="domcontentloaded")
                    await asyncio.sleep(4)
                    body = await page.evaluate("() => document.body.innerText")
                    with open("tax_detail_body.txt", "w", encoding="utf-8") as f:
                        f.write(body)
                    print("Detail body saved to tax_detail_body.txt")
                    print(f"First 1500:\n{body[:1500]}")
                    break

        await browser.close()

asyncio.run(main())

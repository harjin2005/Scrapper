"""Diagnose Montgomery Tax Office — capture exact error and page state."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(30000)

        print("Step 1: Loading index.jsp...")
        try:
            await page.goto(
                "https://actweb.acttax.com/act_webdev/montgomery/index.jsp",
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(3)
            print(f"  URL: {page.url}")
        except Exception as e:
            print(f"  FAILED to load: {e}")
            await browser.close()
            return

        # Print all form inputs
        inputs = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('input,select,button')).map(i=>({
                tag:i.tagName, name:i.name, type:i.type, id:i.id,
                value:i.value, text:(i.innerText||'').slice(0,30)
            }))
        """)
        print(f"\nForm elements:")
        for inp in inputs:
            print(f"  {inp}")

        # Save index HTML
        html = await page.evaluate("() => document.body.innerHTML")
        with open("tax_index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nIndex HTML saved ({len(html)} chars)")

        # Try filling and submitting
        print("\nStep 2: Filling account number...")
        try:
            await page.wait_for_selector("input[name='accountNumber']", timeout=8000)
            await page.fill("input[name='accountNumber']", "000000130387")
            print("  Filled accountNumber field")
        except Exception as e:
            print(f"  No accountNumber field: {e}")
            # Try any text input
            try:
                inputs_els = page.locator("input[type='text']")
                count = await inputs_els.count()
                print(f"  Found {count} text inputs, trying first")
                if count > 0:
                    await inputs_els.first.fill("000000130387")
            except Exception as e2:
                print(f"  Failed: {e2}")

        print("\nStep 3: Submitting...")
        try:
            submit = page.locator("input[type='submit']").first
            if await submit.count() > 0:
                await submit.click()
                print("  Clicked input[type='submit']")
            else:
                btn = page.locator("button[type='submit']").first
                if await btn.count() > 0:
                    await btn.click()
                    print("  Clicked button[type='submit']")
                else:
                    await page.keyboard.press("Enter")
                    print("  Pressed Enter")
        except Exception as e:
            print(f"  Submit failed: {e}")

        await asyncio.sleep(5)
        print(f"\nStep 4: Post-submit URL: {page.url}")

        # All links on result page
        links = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('a')).map(a=>({
                href: a.getAttribute('href'),
                text: a.innerText.trim().slice(0,60)
            }))
        """)
        print(f"\nLinks on result page ({len(links)}):")
        for l in links[:20]:
            print(f"  href={l['href']}  text={l['text']}")

        # Save result HTML
        html2 = await page.evaluate("() => document.body.innerHTML")
        with open("tax_result.html", "w", encoding="utf-8") as f:
            f.write(html2)
        print(f"\nResult HTML saved ({len(html2)} chars)")

        body_text = await page.evaluate("() => document.body.innerText")
        with open("tax_result_text.txt", "w", encoding="utf-8") as f:
            f.write(body_text)
        print(f"Result text saved")
        print(f"\nFirst 800 chars of body:\n{body_text[:800]}")

        await browser.close()

asyncio.run(main())

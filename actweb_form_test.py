
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        p = await b.new_page()
        p.set_default_timeout(30000)
        await p.goto("https://actweb.acttax.com/act_webdev/montgomery/index.jsp")
        await asyncio.sleep(3)
        body = await p.evaluate("() => document.body.innerHTML")
        with open("/tmp/actweb_page.html", "w") as f:
            f.write(body)
        print("saved page")
        await b.close()

asyncio.run(test())

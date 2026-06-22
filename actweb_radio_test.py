import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        p = await b.new_page()
        p.set_default_timeout(30000)
        await p.goto("https://actweb.acttax.com/act_webdev/montgomery/index.jsp")
        await asyncio.sleep(3)

        # Get radio button labels
        radios = await p.evaluate("""() => {
            let radios = document.querySelectorAll('input[name=searchby]');
            return Array.from(radios).map(r => {
                let lbl = document.querySelector('label[for="' + r.id + '"]');
                let nextSib = r.nextSibling;
                return r.value + ': ' + (lbl ? lbl.innerText.trim() : (nextSib ? nextSib.textContent.trim().substring(0,30) : 'no-label'));
            });
        }""")
        print("RADIO OPTIONS:")
        for r in radios:
            print(" ", r)

        # Test value=4 (account number candidate)
        await p.click('input[name=searchby][value="4"]')
        await p.fill('input[name=criteria]', '130387')
        await p.click('input[type=submit]')
        await asyncio.sleep(4)
        body = await p.evaluate("() => document.body.innerText")
        url = p.url
        print("V4 URL:", url)
        print("V4 BODY (first 600):")
        print(body[:600])
        await b.close()

asyncio.run(test())

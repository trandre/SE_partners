"""
Properly dismiss cookie consent via 'Allow All' button,
then interact with the Country filter to load all UK partners.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        api_log = []
        async def on_request(req):
            if "se.com/ww/en/locate/api" in req.url:
                api_log.append({"method": req.method, "url": req.url, "body": req.post_data})

        page.on("request", on_request)
        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        # Wait for cookie consent and click 'Allow All'
        print("Trying to dismiss cookie consent...")
        for sel, description in [
            (".ot-pc-refuse-all-handler", "Necessary Only"),
            (".save-preference-btn-handler", "Confirm Your Choices"),
            ("button:text('Allow All')", "Allow All"),
            ("#onetrust-accept-btn-handler", "Accept All"),
            ("button.allow-all", "Allow All CSS"),
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem and await elem.is_visible():
                    await elem.click()
                    print(f"  Dismissed via: {description}")
                    await asyncio.sleep(2)
                    break
            except:
                pass

        # Verify overlay is gone
        overlay = await page.query_selector(".onetrust-pc-dark-filter")
        overlay_visible = await overlay.is_visible() if overlay else False
        print(f"Cookie overlay still visible: {overlay_visible}")

        if overlay_visible:
            # Force remove
            await page.evaluate("""
                document.querySelectorAll(
                    '#onetrust-consent-sdk, .onetrust-pc-dark-filter, #onetrust-policy'
                ).forEach(e => { e.remove(); });
                document.body.style.overflow = 'auto';
            """)
            print("Force-removed cookie overlay")
            await asyncio.sleep(0.5)

        initial_count = len(api_log)

        # Now interact with the Country filter button
        country_btn = await page.query_selector("button:has-text('Country')")
        if country_btn:
            print("Found [Country] button, clicking...")
            await country_btn.click()
            await asyncio.sleep(2)

            # Look for the text search input for country
            search_inp = await page.query_selector('input[placeholder="Search country"]')
            if search_inp:
                await search_inp.fill("United Kingdom")
                await asyncio.sleep(1)

                # Click the UK option
                await page.evaluate("""
                    (() => {
                        const opts = Array.from(document.querySelectorAll('.pl-option'));
                        const opt = opts.find(o => o.textContent.trim() === 'United Kingdom');
                        if (opt) opt.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        return opt ? 'clicked: ' + opt.textContent : 'not found';
                    })()
                """)
                await asyncio.sleep(8)
        else:
            print("Country button not found, trying direct input")
            inp = await page.query_selector('input[placeholder="Search country"]')
            if inp:
                await inp.fill("United Kingdom")
                await asyncio.sleep(2)
                await page.evaluate("""
                    (() => {
                        const opts = Array.from(document.querySelectorAll('.pl-option'));
                        const opt = opts.find(o => o.textContent.trim() === 'United Kingdom');
                        if (opt) opt.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    })()
                """)
                await asyncio.sleep(6)

        new_calls = api_log[initial_count:]
        print(f"\n{len(new_calls)} NEW API calls:")
        for r in new_calls:
            body = r["body"] or ""
            print(f"  {r['method']} {r['url'][:130]}")
            if body:
                try:
                    b = json.loads(body)
                    if "ids" in b:
                        print(f"    ids[{len(b['ids'])}]: {b['ids'][:8]}")
                    else:
                        print(f"    body: {body[:150]}")
                except:
                    print(f"    body: {body[:150]}")

        # Check current URL (might have changed with country param)
        print(f"\nCurrent URL: {page.url}")

        # Look for any country code in new API calls
        gb_calls = [r for r in new_calls if "countryCode=gb" in r["url"] or "gb" in (r["body"] or "").lower()]
        if gb_calls:
            print(f"\n*** Found UK-specific API call! ***")
            for r in gb_calls:
                print(f"  {r['method']} {r['url']}")
                print(f"  body: {r['body']}")

        await browser.close()

asyncio.run(main())

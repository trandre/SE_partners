"""
Use Playwright's native click to properly trigger the country search.
Also check if there's a map-zoom-out or "show all" button.
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

        new_api_calls = []
        async def on_request(req):
            if "se.com/ww/en/locate/api" in req.url:
                new_api_calls.append({"method": req.method, "url": req.url, "body": req.post_data})

        page.on("request", on_request)
        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        initial_count = len(new_api_calls)
        print(f"After page load: {initial_count} API calls")
        for r in new_api_calls:
            print(f"  {r['method']} {r['url'][:110]} {(r['body'] or '')[:80]}")

        # Remove overlays
        await page.evaluate("""
            document.querySelectorAll('#onetrust-consent-sdk, .onetrust-pc-dark-filter').forEach(e => e.remove());
            document.body.style.overflow = 'auto';
        """)
        await asyncio.sleep(0.3)

        # Use Playwright text matching to click country option
        inp = await page.query_selector('input[placeholder="Search country"]')
        if inp:
            # Scroll to it first
            await inp.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)
            await inp.fill("United Kingdom")
            await asyncio.sleep(2)

            # Use Playwright locator to click the "United Kingdom" option
            try:
                uk_locator = page.locator('.pl-option', has_text="United Kingdom").first
                await uk_locator.click(timeout=5000)
                print("Clicked UK option via Playwright locator")
                await asyncio.sleep(6)
            except Exception as e:
                print(f"Locator click failed: {e}")
                # Fallback: use JS with proper Svelte event dispatch
                await page.evaluate("""
                    (() => {
                        const opts = Array.from(document.querySelectorAll('.pl-option'));
                        const opt = opts.find(o => o.textContent.trim() === 'United Kingdom');
                        if (opt) {
                            // Dispatch synthetic mouse events
                            opt.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                            opt.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                            opt.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            return 'dispatched events on ' + opt.textContent.trim();
                        }
                        return 'not found';
                    })()
                """)
                await asyncio.sleep(6)

        new_calls = new_api_calls[initial_count:]
        print(f"\n{len(new_calls)} NEW API calls after country select:")
        for r in new_calls:
            body = (r["body"] or "")
            print(f"  {r['method']} {r['url'][:130]}")
            if body:
                try:
                    b = json.loads(body)
                    if "ids" in b:
                        print(f"    ids: {b['ids'][:5]}... ({len(b['ids'])} total)")
                    else:
                        print(f"    body: {body[:150]}")
                except:
                    print(f"    body: {body[:150]}")

        # Take a screenshot to see current page state
        await page.screenshot(path="/home/powerq001/getVendors/page_state.png")
        print("Screenshot saved to page_state.png")

        # Look for any "show all" or "list" view elements
        all_btns = await page.evaluate("""
            Array.from(document.querySelectorAll('button, a, [role=button]'))
                .filter(e => e.offsetHeight > 0)
                .map(e => ({text: e.textContent.trim().substring(0,40), cls: e.className.substring(0,50)}))
                .filter(e => e.text.length > 0 && e.text.length < 40)
                .slice(0, 20)
        """)
        print("\nVisible buttons:")
        for b in all_btns:
            print(f"  [{b['text']}] cls={b['cls']}")

        await browser.close()

asyncio.run(main())

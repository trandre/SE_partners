"""
Properly select a country to trigger the partner search API.
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
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        initial_count = len(api_log)
        print(f"Initial API calls: {initial_count}")

        # Remove cookie overlays via JS
        await page.evaluate("""
            document.querySelectorAll('#onetrust-consent-sdk, .onetrust-pc-dark-filter').forEach(e => e.remove());
        """)
        await asyncio.sleep(0.3)

        # Find and click the country search
        inp = await page.query_selector('input[placeholder="Search country"]')
        if inp:
            await inp.click(force=True)
            await asyncio.sleep(0.5)
            await inp.fill("United Kingdom")
            await asyncio.sleep(2)

            # Click the "United Kingdom" option specifically (class=pl-option)
            clicked = await page.evaluate("""
                (() => {
                    const opts = Array.from(document.querySelectorAll('.pl-option'));
                    const ukOpt = opts.find(o => o.textContent.trim() === 'United Kingdom');
                    if (ukOpt) {
                        ukOpt.click();
                        return 'clicked: ' + ukOpt.textContent.trim();
                    }
                    return 'not found, options: ' + opts.map(o => o.textContent.trim()).slice(0,5).join(', ');
                })()
            """)
            print(f"Country select: {clicked}")
            await asyncio.sleep(8)  # Wait for search API to fire

        print(f"\nAPI calls after country select ({len(api_log)} total, {len(api_log)-initial_count} new):")
        for req in api_log[initial_count:]:
            body_preview = (req["body"] or "")[:150]
            print(f"  {req['method']:4} {req['url'][:130]}")
            if body_preview:
                print(f"        body: {body_preview}")

        # Also capture any responses
        if len(api_log) > initial_count:
            # Try to repeat the POST that resulted in data
            for req in api_log[initial_count:]:
                if "id-list" in req["url"] or "search" in req["url"]:
                    print(f"\n  → Found interesting call: {req['url'][:100]}")
                    print(f"    body: {req['body'][:200] if req['body'] else 'none'}")

        await browser.close()

asyncio.run(main())

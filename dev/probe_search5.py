"""
Bypass OneTrust cookie consent by injecting consent cookies/localStorage
BEFORE page load. Then interact with the Country filter.
"""
import asyncio, json, time
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

# Pre-set OneTrust consent via cookies (avoids modal entirely)
CONSENT_COOKIES = [
    {
        "name": "OptanonAlertBoxClosed",
        "value": "2024-01-01T00:00:00.000Z",
        "domain": ".se.com",
        "path": "/",
    },
    {
        "name": "OptanonConsent",
        "value": (
            "isGpcEnabled=0&datestamp=Mon+Jan+01+2024+00%3A00%3A00+GMT%2B0000&version=202209.1.0"
            "&isIABGlobal=false&hosts=&consentId=test&interactionCount=1&landingPath=NotLandingPage"
            "&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1&AwaitingReconsent=false"
        ),
        "domain": ".se.com",
        "path": "/",
    },
]

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

        # Add consent cookies before loading page
        await ctx.add_cookies(CONSENT_COOKIES)

        # Also inject a script to suppress the modal
        await ctx.add_init_script("""
            // Pre-set OneTrust consent in localStorage
            Object.defineProperty(window, 'OptanonWrapper', {
                get: () => () => {},
                set: () => {}
            });
            // Block OneTrust from showing modal
            const _origSetItem = Storage.prototype.setItem;
            Storage.prototype.setItem = function(key, val) {
                if (key && key.includes('OneTrust')) return;
                return _origSetItem.apply(this, arguments);
            };
        """)

        page = await ctx.new_page()

        api_log = []
        async def on_request(req):
            if "se.com/ww/en/locate/api" in req.url:
                api_log.append({"method": req.method, "url": req.url, "body": req.post_data})

        page.on("request", on_request)
        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        # Check if overlay exists
        overlay_count = await page.evaluate("""
            document.querySelectorAll('.onetrust-pc-dark-filter, #onetrust-consent-sdk').length
        """)
        print(f"Cookie overlay elements: {overlay_count}")

        # Force remove any remaining overlays
        await page.evaluate("""
            document.querySelectorAll(
                '#onetrust-consent-sdk, .onetrust-pc-dark-filter, #onetrust-banner-sdk'
            ).forEach(e => e.remove());
            document.body.style.overflow = 'auto';
            document.body.style.pointerEvents = 'auto';
        """)

        initial_count = len(api_log)
        print(f"API calls so far: {initial_count}")
        for r in api_log:
            print(f"  {r['method']} {r['url'][:100]} {(r['body'] or '')[:80]}")

        # Now click the Country button using force=True to bypass any overlay
        country_btn = page.locator("button", has_text="Country").first
        try:
            await country_btn.click(force=True, timeout=5000)
            print("Clicked [Country] button")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Country button click failed: {e}")

        # Type in country search
        inp = page.locator('input[placeholder="Search country"]').first
        try:
            await inp.fill("United Kingdom", timeout=5000)
            await asyncio.sleep(1.5)
            print("Typed United Kingdom")
        except Exception as e:
            print(f"Search input failed: {e}")

        # Click UK option with force=True
        uk_option = page.locator('.pl-option', has_text="United Kingdom").first
        try:
            await uk_option.click(force=True, timeout=5000)
            print("Clicked United Kingdom option")
            await asyncio.sleep(8)
        except Exception as e:
            print(f"UK option click failed: {e}")

        new_calls = api_log[initial_count:]
        print(f"\n{len(new_calls)} NEW API calls after country select:")
        for r in new_calls:
            body = r["body"] or ""
            print(f"  {r['method']} {r['url'][:140]}")
            if body:
                try:
                    b = json.loads(body)
                    if "ids" in b:
                        print(f"    → {len(b['ids'])} IDs: {b['ids'][:5]}...")
                    else:
                        print(f"    → {body[:200]}")
                except:
                    print(f"    → {body[:200]}")

        await browser.close()

asyncio.run(main())

"""
Probe the SE Locator Svelte app's internal state and intercept
all API calls to discover the full pagination strategy.
"""
import asyncio, json, re
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        api_log = []
        async def on_request(req):
            if "se.com" in req.url and ("locate/api" in req.url or "partner" in req.url.lower()):
                api_log.append(f"REQ: {req.url}")
        async def on_response(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct and "se.com" in r.url:
                try:
                    d = await r.json()
                    api_log.append(f"RSP [{r.status}] {r.url} → {type(d).__name__}[{len(d) if isinstance(d,list) else '?'}]")
                except:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        print("Loading page …")
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)

        # Accept cookies
        for sel in ["#onetrust-accept-btn-handler", "button[id*=accept]"]:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    print(f"Cookie consent dismissed via {sel}")
                    await asyncio.sleep(2)
                    break
            except:
                pass

        # Force-remove cookie overlay via JS
        await page.evaluate("""
            ['#onetrust-consent-sdk', '.onetrust-pc-dark-filter'].forEach(s => {
                const el = document.querySelector(s);
                if (el) el.remove();
            });
        """)
        await asyncio.sleep(1)

        # Scroll to load any lazy content
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(2)

        # Check the Svelte app's window.__data__ or similar
        app_data = await page.evaluate("""
            (() => {
                const result = {};
                // Check common Svelte/app state patterns
                if (window.__PARTNER_LOCATOR_DATA__) result.partnerData = window.__PARTNER_LOCATOR_DATA__;
                if (window.__APP_DATA__) result.appData = window.__APP_DATA__;
                if (window.__INIT_DATA__) result.initData = window.__INIT_DATA__;
                // Check for Svelte stores or component state
                const svelte = document.querySelector('[data-svelte-h]') || document.querySelector('[data-sveltekit-reload]');
                if (svelte) result.hasSvelte = true;
                // Look for JSON in script tags
                const scripts = Array.from(document.querySelectorAll('script:not([src])'));
                result.inlineScripts = scripts
                    .map(s => s.textContent.substring(0, 200))
                    .filter(t => t.includes('partner') || t.includes('locate') || t.includes('config'));
                return result;
            })()
        """)
        print("App data:", json.dumps(app_data, indent=2)[:1000])

        # Look at all network requests made
        print("\n=== API Log ===")
        for entry in api_log:
            print(f"  {entry[:150]}")

        # Try to get the country list from the app
        country_data = await page.evaluate("""
            (() => {
                // Look for country list in any global variable
                for (const key of Object.keys(window)) {
                    const val = window[key];
                    if (val && typeof val === 'object' && !Array.isArray(val)) {
                        for (const [k, v] of Object.entries(val)) {
                            if (k.toLowerCase().includes('countr') && Array.isArray(v) && v.length > 10) {
                                return {key: key + '.' + k, data: v.slice(0, 5)};
                            }
                        }
                    }
                }
                return null;
            })()
        """)
        print("\nCountry data:", json.dumps(country_data, indent=2)[:500])

        # Look at __svelte__ context
        svelte_ctx = await page.evaluate("""
            (() => {
                const ctx = document.querySelector('#svelte') || document.querySelector('[id^=svelte]');
                if (!ctx) return 'no svelte root';
                return ctx.id + ' children:' + ctx.children.length;
            })()
        """)
        print("\nSvelte root:", svelte_ctx)

        await browser.close()

asyncio.run(main())

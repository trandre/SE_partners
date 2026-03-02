"""Check the 400 detail on id-list, find the right coordinate/location params."""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = "https://www.se.com/ww/en/locate/221-find-an-industrial-automation-distributor-near-you"
CONSENT_COOKIES = [
    {"name": "OptanonAlertBoxClosed", "value": "2024-01-01T00:00:00.000Z",
     "domain": ".se.com", "path": "/"},
    {"name": "OptanonConsent",
     "value": "isGpcEnabled=0&consentId=test&interactionCount=1&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1",
     "domain": ".se.com", "path": "/"},
]

async def jfetch(page, url):
    return await page.evaluate(f"""
        fetch('{url}', {{headers: {{"Accept": "application/json"}}}})
            .then(async r => ({{status: r.status, body: await r.text()}}))
            .catch(e => ({{error: e.toString()}}))
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        await ctx.add_cookies(CONSENT_COOKIES)
        page = await ctx.new_page()

        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(4)

        # Check the 400 detail
        r = await jfetch(page, "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww")
        print("id-list 400 detail:", r.get("body", "")[:500])

        # Try with lat/lon (based on the location-based nature of the app)
        location_tests = [
            "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&latitude=51.5&longitude=-0.1",
            "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&lat=51.5&lon=-0.1",
            "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&location=51.5,-0.1",
            # Maybe it needs a 'radius' too
            "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&latitude=0&longitude=0&radius=40000",
            # Try with just location params, no countryCode
            "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&latitude=51.5&longitude=-0.1",
            # Check what's in the real initial POST call
            # The POST is to id-list-grouped with IDs. Where do those come from?
            # Maybe there's a different path like 'ids' endpoint
            "/ww/en/locate/api/partners/ids?configurationId=221&languageCode=en&countryCode=ww",
            "/ww/en/locate/api/partners?configurationId=221&languageCode=en&countryCode=ww&page=1&pageSize=50",
            # Try with 'globalSearch' which appeared in JS
            "/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&globalSearch=true",
        ]

        print("\n=== Location-based tests ===")
        for url in location_tests:
            r = await jfetch(page, url)
            status = r.get("status")
            try:
                body = json.loads(r.get("body", ""))
                if isinstance(body, list):
                    print(f"  [{len(body):>6}]  HTTP{status}  {url.split('?')[1][:100]}")
                    if body:
                        print(f"           sample: {body[:5]}")
                elif isinstance(body, dict):
                    detail = body.get("detail", body.get("message", body.get("code", str(body)[:80])))
                    print(f"  [dict]    HTTP{status}  detail={detail[:100]}  {url.split('?')[1][:60]}")
            except:
                print(f"  [raw]     HTTP{status}  {r.get('body','')[:100]}")

        # Also try to access the Svelte app's internal store
        store_data = await page.evaluate("""
            (() => {
                // Try to find the locator data store
                const stores = [];
                // Walk window to find anything with 'ids' array
                function walk(obj, depth, path) {
                    if (depth > 3 || typeof obj !== 'object' || obj === null) return;
                    for (const [k, v] of Object.entries(obj)) {
                        if (k === 'ids' && Array.isArray(v) && v.length > 10) {
                            stores.push({path: path+'.'+k, len: v.length, sample: v.slice(0,5)});
                        }
                        if (typeof v === 'object' && v !== null) walk(v, depth+1, path+'.'+k);
                    }
                }
                walk(window, 0, 'window');
                return stores;
            })()
        """)
        print(f"\nStores with 'ids' arrays: {store_data}")

        await browser.close()

asyncio.run(main())

"""
Test the api/partners/locations endpoint which returns all partner IDs + coordinates.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = "https://www.se.com/ww/en/locate/221-find-an-industrial-automation-distributor-near-you"

async def jfetch_full(page, url, method="GET", body=None):
    opts = {"method": method, "headers": {"Accept": "application/json"}}
    if body is not None:
        opts["body"] = json.dumps(body)
        opts["headers"]["Content-Type"] = "application/json"
    opts_js = json.dumps(opts)
    return await page.evaluate(f"""
        fetch('{url}', {opts_js})
            .then(async r => ({{status: r.status, body: await r.text()}}))
            .catch(e => ({{error: e.toString()}}))
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(4)

        # Test the locations endpoint with various params
        BASE = "/ww/en/locate/api/partners/locations"
        tests = [
            # Basic with just configurationId
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww",
            # With bounding box (full world)
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&neLat=90&neLng=180&swLat=-90&swLng=-180",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ne_lat=90&ne_lng=180&sw_lat=-90&sw_lng=-180",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&bounds=90,180,-90,-180",
            # With radius from center of world
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&lat=0&lng=0&radius=40000",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&latitude=0&longitude=0&radius=40000",
            # Without countryCode
            f"{BASE}?configurationId=221&languageCode=en",
            # Just configurationId
            f"{BASE}?configurationId=221",
            # POST variant
        ]

        print("=== GET tests ===")
        for url in tests:
            r = await jfetch_full(page, url)
            status = r.get("status")
            try:
                body = json.loads(r.get("body", ""))
                if isinstance(body, dict):
                    keys = list(body.keys())[:6]
                    total = body.get("totalCount", body.get("total", body.get("count", "")))
                    pl = body.get("partnerLocations", [])
                    print(f"  HTTP{status} keys={keys} total={total} pl_len={len(pl)}  {url.split('?')[1][:80]}")
                    if pl:
                        print(f"    partnerLocations sample: {json.dumps(pl[0])[:150]}")
                    if "detail" in body:
                        print(f"    detail: {body['detail']}")
                elif isinstance(body, list):
                    print(f"  HTTP{status} [{len(body)}]  {url.split('?')[1][:80]}")
            except:
                print(f"  HTTP{status} raw: {r.get('body','')[:100]}  {url.split('?')[1][:60]}")

        # POST test
        print("\n=== POST tests ===")
        for body_data in [
            {"configurationId": 221, "languageCode": "en", "countryCode": "ww"},
            {"configurationId": 221, "languageCode": "en", "countryCode": "ww",
             "bounds": {"ne": {"lat": 90, "lng": 180}, "sw": {"lat": -90, "lng": -180}}},
            {"configurationId": 221, "languageCode": "en",
             "location": {"lat": 0, "lng": 0}, "radius": 40000},
        ]:
            r = await jfetch_full(page, BASE, method="POST", body=body_data)
            status = r.get("status")
            try:
                body = json.loads(r.get("body", ""))
                if isinstance(body, dict):
                    pl = body.get("partnerLocations", [])
                    print(f"  POST HTTP{status} keys={list(body.keys())[:5]} pl_len={len(pl)}")
                    if "detail" in body:
                        print(f"    detail: {body['detail']}")
                else:
                    print(f"  POST HTTP{status} {str(body)[:80]}")
            except:
                print(f"  POST HTTP{status} {r.get('body','')[:100]}")

        # Also try to find the actual call parameters from the app's network interceptor
        # Look at what params the Svelte app sends to the locations endpoint
        actual_calls = await page.evaluate("""
            performance.getEntriesByType('resource')
                .filter(e => e.name.includes('locations'))
                .map(e => e.name)
        """)
        print(f"\nActual 'locations' API calls made: {actual_calls}")

        await browser.close()

asyncio.run(main())

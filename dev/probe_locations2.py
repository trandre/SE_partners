"""
Test api/partners/locations with 'config' parameter.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = "https://www.se.com/ww/en/locate/221-find-an-industrial-automation-distributor-near-you"
BASE = "/ww/en/locate/api/partners/locations"

async def jfetch(page, url):
    return await page.evaluate(f"""
        fetch('{url}', {{headers: {{"Accept": "application/json"}}}})
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

        # Capture the actual 'locations' call from the app if any
        locs_calls = []
        async def on_req(req):
            if "locations" in req.url and "locate/api" in req.url:
                locs_calls.append(req.url)
        page.on("request", on_req)

        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(6)

        print(f"App-made 'locations' calls: {locs_calls}")

        tests = [
            f"{BASE}?config=221&languageCode=en&countryCode=ww",
            f"{BASE}?config=221&lc=en&cc=ww",
            f"{BASE}?config=221&languageCode=en",
            f"{BASE}?config=221",
            # Maybe the map needs to be visible and makes the call
            f"{BASE}?config=221&languageCode=en&countryCode=ww&zoom=1&neLat=90&neLng=180&swLat=-90&swLng=-180",
            f"{BASE}?config=221&languageCode=en&countryCode=ww&zoom=0",
            f"{BASE}?configId=221&languageCode=en&countryCode=ww",
            f"{BASE}?configurationId=221&lc=en&cc=ww",
        ]

        print("\n=== Testing with 'config' param ===")
        for url in tests:
            r = await jfetch(page, url)
            status = r.get("status")
            try:
                body = json.loads(r.get("body", ""))
                if isinstance(body, dict):
                    pl = body.get("partnerLocations", [])
                    detail = body.get("detail", "")
                    total = body.get("totalCount", body.get("total", ""))
                    print(f"  HTTP{status} pl={len(pl)} total={total} detail={detail[:80]}  {url.split('?')[1][:80]}")
                    if pl:
                        print(f"    Sample: {json.dumps(pl[0])[:200]}")
                elif isinstance(body, list):
                    print(f"  HTTP{status} [{len(body)}]  {url.split('?')[1][:80]}")
            except:
                print(f"  HTTP{status} {r.get('body','')[:80]}")

        # Also look at what the Svelte app sends to the map
        # Wait for the map to initialize and make a locations call
        # Try scrolling to trigger map load
        await page.evaluate("window.scrollTo(0, 500)")
        await asyncio.sleep(5)

        print(f"\nNew 'locations' calls after scroll: {locs_calls}")

        # Look at real call URL if any
        if locs_calls:
            for url in locs_calls:
                r = await jfetch(page, url)
                status = r.get("status")
                try:
                    body = json.loads(r.get("body", ""))
                    pl = body.get("partnerLocations", [])
                    print(f"  REAL CALL [{len(pl)}]  {url[:150]}")
                    if pl:
                        print(f"    Sample: {json.dumps(pl[0])[:200]}")
                except:
                    print(f"  REAL CALL  {r.get('body','')[:100]}")

        await browser.close()

asyncio.run(main())

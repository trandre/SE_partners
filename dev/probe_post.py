"""
The id-list-grouped endpoint uses POST. Capture the request body and test
pagination via POST with different country codes and page parameters.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)
API_PATH = "/ww/en/locate/api/partners/id-list-grouped"

COMMON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "referer": TARGET,
}

async def jpost(page, url, body=None):
    body_js = json.dumps(body) if body else '"{}"'
    return await page.evaluate(f"""
        fetch('{url}', {{
            method: 'POST',
            headers: {json.dumps(COMMON_HEADERS)},
            body: {body_js if body is None else "JSON.stringify(" + json.dumps(body) + ")"}
        }}).then(async r => ({{status: r.status, body: await r.text()}}))
          .catch(e => ({{error: e.toString()}}))
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Capture POST body of original request
        post_body = {}
        async def on_request(req):
            nonlocal post_body
            if "id-list-grouped" in req.url and req.method == "POST":
                try:
                    raw = req.post_data
                    post_body = json.loads(raw) if raw else {}
                    print(f"POST body: {raw!r}")
                except:
                    post_body = {}

        page.on("request", on_request)
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)

        print(f"Captured POST body: {post_body}")

        # Dismiss cookies
        for sel in ["#onetrust-accept-btn-handler"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except:
                pass

        # Test POST to the endpoint
        ts = int(await page.evaluate("Date.now()"))
        base_url = f"{API_PATH}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}"

        print("\n=== POST with captured body ===")
        r = await jpost(page, base_url, post_body if post_body else None)
        print(f"Status: {r.get('status')}")
        try:
            d = json.loads(r.get('body',''))
            print(f"Type: {type(d).__name__}, len: {len(d) if isinstance(d,list) else '?'}")
            if isinstance(d, list) and d:
                print(f"Sample keys: {list(d[0].keys())[:8]}")
        except:
            print(f"Body: {r.get('body','')[:200]}")

        # Test with various POST bodies
        print("\n=== POST with pagination bodies ===")
        test_bodies = [
            {},
            {"pageSize": 50, "pageNumber": 1},
            {"pageSize": 100, "pageNumber": 1},
            {"pageSize": 50, "page": 1},
            {"limit": 50, "offset": 0},
            {"size": 50, "from": 0},
            {"filters": {}, "pageSize": 50, "pageNumber": 1},
            None,  # no body
        ]
        for body in test_bodies:
            for cc in ["ww", "gb", "fr", "de"]:
                ts2 = int(await page.evaluate("Date.now()"))
                url = f"{API_PATH}?configurationId=221&languageCode=en&countryCode={cc}&ts={ts2}"
                r = await jpost(page, url, body)
                status = r.get('status')
                try:
                    d = json.loads(r.get('body',''))
                    n = len(d) if isinstance(d, list) else str(d.get('code','?'))
                    print(f"  cc={cc} body={json.dumps(body)[:40]:40} → HTTP{status} [{n}]")
                except:
                    print(f"  cc={cc} body={json.dumps(body)[:40]:40} → HTTP{status} {r.get('body','')[:60]}")

        await browser.close()

asyncio.run(main())

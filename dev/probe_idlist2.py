"""
Test the discovered api/partners/id-list endpoint.
The Svelte app uses this to get ALL partner IDs, then POSTs them
to id-list-grouped for full details.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

CONSENT_COOKIES = [
    {"name": "OptanonAlertBoxClosed", "value": "2024-01-01T00:00:00.000Z",
     "domain": ".se.com", "path": "/"},
    {"name": "OptanonConsent",
     "value": "isGpcEnabled=0&consentId=test&interactionCount=1&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1",
     "domain": ".se.com", "path": "/"},
]

async def jfetch(page, url, method="GET", body=None):
    opts = {"method": method, "headers": {"Accept": "application/json"}}
    if body is not None:
        opts["body"] = json.dumps(body)
        opts["headers"]["Content-Type"] = "application/json"
    return await page.evaluate(f"""
        fetch('{url}', {json.dumps(opts)})
            .then(async r => ({{status: r.status, body: await r.text()}}))
            .catch(e => ({{error: e.toString()}}))
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        await ctx.add_cookies(CONSENT_COOKIES)
        page = await ctx.new_page()

        # Capture the real API calls made by the app for reference
        real_calls = []
        async def on_req(req):
            if "locate/api" in req.url:
                real_calls.append({"method": req.method, "url": req.url, "body": req.post_data})
        page.on("request", on_req)

        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(6)

        print("=== Real API calls on load ===")
        for r in real_calls:
            print(f"  {r['method']} {r['url'][:130]} {(r['body'] or '')[:80]}")

        # Test the id-list endpoint
        ts = int(await page.evaluate("Date.now()"))
        tests = [
            # GET variants
            f"/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&ts={ts}",
            f"/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww",
            f"/ww/en/locate/api/partners/id-list?configurationId=221&countryCode=ww",
            f"/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=gb",
            f"/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=fr",
            # Also check the actual URL format the Svelte app uses
            f"/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww&pageSize=100",
        ]

        print("\n=== Testing id-list endpoint ===")
        for url in tests:
            r = await jfetch(page, url)
            status = r.get('status')
            try:
                body = json.loads(r.get('body', ''))
                if isinstance(body, list):
                    print(f"  [{len(body):>6}]  HTTP{status}  {url.split('?')[1][:80]}")
                    if body:
                        print(f"           sample: {body[:5]}")
                elif isinstance(body, dict):
                    print(f"  [dict:{list(body.keys())[:4]}]  HTTP{status}  {url.split('?')[1][:80]}")
                    if "message" in body:
                        print(f"           message: {body.get('message','')[:100]}")
            except:
                print(f"  [raw]  HTTP{status}  {r.get('body','')[:100]}  {url.split('?')[1][:60]}")

        # Try with POST
        print("\n=== id-list via POST ===")
        for body_data in [
            None,
            {"configurationId": 221, "languageCode": "en", "countryCode": "ww"},
        ]:
            url = f"/ww/en/locate/api/partners/id-list?configurationId=221&languageCode=en&countryCode=ww"
            r = await jfetch(page, url, method="POST", body=body_data)
            status = r.get("status")
            body_text = r.get("body", "")
            try:
                d = json.loads(body_text)
                n = len(d) if isinstance(d, list) else str(d)[:80]
                print(f"  POST body={json.dumps(body_data)[:40]} → HTTP{status} [{n}]")
            except:
                print(f"  POST body={json.dumps(body_data)[:40]} → HTTP{status} {body_text[:80]}")

        # Also look at the Svelte app internal state to find the ID list
        svelte_state = await page.evaluate("""
            (() => {
                // Try to access Svelte component internals
                const app = document.querySelector('#svelte-app') || document.querySelector('[data-sveltekit-scroll]') || document.body.firstElementChild;
                if (app && app.__svelte__) return JSON.stringify(app.__svelte__).substring(0, 500);
                // Try window variables
                const keys = Object.keys(window).filter(k => k.includes('locator') || k.includes('partner') || k.includes('Locator'));
                return keys.join(', ') || 'no svelte state found';
            })()
        """)
        print(f"\nSvelte state: {svelte_state}")

        await browser.close()

asyncio.run(main())

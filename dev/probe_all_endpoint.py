"""
Test the /partners/all endpoint which returned 400 — inspect the error detail
and try variations. Also test with fresh ts and different URL patterns.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

async def jfetch_full(page, url, method="GET", body=None):
    """Fetch with full response details."""
    opts = f"""{{method: '{method}',
        headers: {{'Accept': 'application/json', 'Content-Type': 'application/json'}}
        {',' + "'body': JSON.stringify(" + json.dumps(body) + ")" if body else ''}
    }}"""
    return await page.evaluate(f"""
        fetch('{url}', {opts}).then(async r => ({{
            status: r.status,
            headers: Object.fromEntries(r.headers),
            body: await r.text()
        }})).catch(e => ({{error: e.toString()}}))
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)
        for sel in ["#onetrust-accept-btn-handler"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except:
                pass

        # Test with FRESH timestamp (key difference!)
        fresh_ts = int(await page.evaluate("Date.now()"))
        print(f"Fresh ts: {fresh_ts}")

        tests_with_fresh_ts = [
            f"/ww/en/locate/api/partners/id-list-grouped?configurationId=221&languageCode=en&countryCode=ww&ts={fresh_ts}",
            f"/ww/en/locate/api/partners/id-list-grouped?configurationId=221&languageCode=en&countryCode=ww&ts={fresh_ts}&pageSize=100",
            f"/ww/en/locate/api/partners/id-list-grouped?configurationId=221&languageCode=en&countryCode=ww&ts={fresh_ts}&pageSize=100&pageNumber=2",
            f"/ww/en/locate/api/partners/id-list-grouped?configurationId=221&languageCode=en&countryCode=fr&ts={fresh_ts}",
            f"/ww/en/locate/api/partners/id-list-grouped?configurationId=221&languageCode=en&countryCode=gb&ts={fresh_ts}",
            f"/ww/en/locate/api/partners/id-list-grouped?configurationId=221&languageCode=en&countryCode=de&ts={fresh_ts}",
        ]

        print("\n=== Fresh timestamp tests ===")
        for url in tests_with_fresh_ts:
            r = await jfetch_full(page, url)
            status = r.get('status')
            body_text = r.get('body', '')[:300]
            try:
                body_json = json.loads(body_text)
                if isinstance(body_json, list):
                    print(f"  [{len(body_json):>5}] HTTP{status}  {url.split('?')[1][:80]}")
                else:
                    print(f"  [dict]  HTTP{status}  {body_json}  {url.split('?')[1][:60]}")
            except:
                print(f"  [raw]   HTTP{status}  {body_text[:100]}  {url.split('?')[1][:60]}")

        # Check the 400 /all endpoint
        print("\n=== /all endpoint detail ===")
        r = await jfetch_full(page, "/ww/en/locate/api/partners/all?configurationId=221&languageCode=en")
        print(f"  Status: {r.get('status')}")
        print(f"  Body: {r.get('body','')[:500]}")

        # Try POST on the partners endpoint
        print("\n=== POST to partners endpoint ===")
        post_tests = [
            ("/ww/en/locate/api/partners/search",
             {"configurationId": 221, "languageCode": "en", "countryCode": "ww"}),
            ("/ww/en/locate/api/partners",
             {"configurationId": 221, "languageCode": "en", "countryCode": "ww", "pageSize": 50, "pageNumber": 1}),
        ]
        for url, body in post_tests:
            r = await jfetch_full(page, url, method="POST", body=body)
            print(f"  POST {url}: HTTP{r.get('status')} → {r.get('body','')[:200]}")

        await browser.close()

asyncio.run(main())

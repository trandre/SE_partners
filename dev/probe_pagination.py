"""
Test all pagination strategies for the SE id-list-grouped endpoint.
Also try alternate API endpoints that might return all distributors.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)
BASE = "/ww/en/locate/api/partners/id-list-grouped"

async def jfetch(page, url):
    return await page.evaluate(f"""
        fetch('{url}').then(r => r.json()).catch(e => ({{error: e.toString()}}))
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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

        ts = "1772489747730"

        # ── Test pagination params on the known working URL ───────────────
        tests = [
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}&pageSize=50&pageNumber=1",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}&pageSize=50&page=1",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}&limit=50&offset=0",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}&size=50&from=0",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}&count=50&startIndex=0",
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww&ts={ts}&take=50&skip=0",
            # Without ts
            f"{BASE}?configurationId=221&languageCode=en&countryCode=ww",
            # Try alternate endpoints
            "/ww/en/locate/api/partners?configurationId=221&languageCode=en&countryCode=ww",
            "/ww/en/locate/api/partners/list?configurationId=221&languageCode=en&countryCode=ww",
            "/ww/en/locate/api/partners/all?configurationId=221&languageCode=en",
            "/ww/en/locate/api/partners/search?configurationId=221&languageCode=en&countryCode=ww",
            "/ww/en/locate/api/partners?programId=221&countryCode=ww",
            # Try the configurations endpoint (analytics works differently)
            "/ww/en/locate/api/configurations/221",
            "/ww/en/locate/api/configurations",
        ]

        print("=== Pagination / alternate endpoint tests ===")
        for url in tests:
            try:
                d = await jfetch(page, url)
                if isinstance(d, list):
                    print(f"  [{len(d):>5}] {url[:110]}")
                elif isinstance(d, dict):
                    keys = list(d.keys())[:6]
                    status = d.get('status', d.get('code', ''))
                    n = d.get('total', d.get('totalCount', d.get('count', '')))
                    print(f"  [dict] keys={keys} status={status} total={n}  {url[:80]}")
            except Exception as e:
                print(f"  [ERR]  {e}  {url[:80]}")

        # ── Try searching by triggering a country search programmatically ──
        print("\n=== Testing country-based search via app functions ===")
        countries_test = ["fr", "de", "us", "br", "au", "in", "cn", "es", "it", "pl"]
        for cc in countries_test:
            try:
                url = f"{BASE}?configurationId=221&languageCode=en&countryCode={cc}&ts={ts}"
                d = await jfetch(page, url)
                if isinstance(d, list):
                    print(f"  cc={cc}: {len(d)} records")
                else:
                    msg = d.get('message', d.get('code', str(d)[:60]))
                    print(f"  cc={cc}: {msg}")
            except Exception as e:
                print(f"  cc={cc}: {e}")

        await browser.close()

asyncio.run(main())

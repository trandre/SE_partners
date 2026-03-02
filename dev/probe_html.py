"""
Examine the HTML source directly for embedded partner IDs / search API clues.
Also scan JS for the 'search' or 'filter' endpoint that returns all IDs.
"""
import asyncio, json, re
from playwright.async_api import async_playwright

TARGET = "https://www.se.com/ww/en/locate/221-find-an-industrial-automation-distributor-near-you"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        page = await ctx.new_page()
        js_files = {}
        async def on_resp(r):
            if "javascript" in r.headers.get("content-type","") and "svelte_app" in r.url:
                try:
                    js_files[r.url.split("/")[-1]] = await r.text()
                except: pass

        page.on("response", on_resp)
        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(4)

        html = await page.content()
        # Look for JSON data in HTML
        json_blobs = re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.S)
        for i, blob in enumerate(json_blobs):
            print(f"JSON blob {i}: {blob[:500]}")

        # Look for partner data patterns
        partner_ids_in_html = re.findall(r'"id"\s*:\s*(\d{5,6})', html)
        print(f"\nPartner IDs in HTML: {len(partner_ids_in_html)} found: {partner_ids_in_html[:20]}")

        # Check for API URL patterns
        api_patterns = re.findall(r'(?:api|locate)[^"\'<> ]{5,100}', html)
        se_apis = [p for p in api_patterns if 'partner' in p.lower() or 'locate' in p.lower()]
        print(f"\nAPI patterns in HTML: {se_apis[:10]}")

        # Now scan JS files for search endpoint
        print(f"\n=== Scanning {len(js_files)} JS files ===")
        for fname, content in js_files.items():
            hits = []
            for pattern in ['search', 'filter', 'find-partner', 'findPartners',
                           'getAllIds', 'getIds', '/ids', 'totalCount', 'totalResults',
                           'api/partners/', 'pageNumber']:
                if pattern in content:
                    idx = content.find(pattern)
                    ctx_snip = content[max(0,idx-80):idx+200]
                    hits.append(f"  [{pattern}]: {ctx_snip[:250]}")
            if hits:
                print(f"\n{fname}:")
                for h in hits[:5]:
                    print(h)

        # Also look at ALL XHR made during the page - capture their URLs
        all_urls = await page.evaluate("""
            // Access performance entries for network requests
            performance.getEntriesByType('resource')
                .filter(e => e.initiatorType === 'xmlhttprequest' || e.initiatorType === 'fetch')
                .map(e => e.name)
        """)
        print(f"\nXHR/fetch requests made: {len(all_urls)}")
        for url in all_urls:
            print(f"  {url[:150]}")

        await browser.close()

asyncio.run(main())

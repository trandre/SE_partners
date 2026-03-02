"""
Check the page HTML for embedded data and investigate the Svelte app JS
for the IDs source / search API pattern.
"""
import asyncio, json, re
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

CONSENT_COOKIES = [
    {"name": "OptanonAlertBoxClosed", "value": "2024-01-01T00:00:00.000Z",
     "domain": ".se.com", "path": "/"},
    {"name": "OptanonConsent",
     "value": "isGpcEnabled=0&datestamp=Mon+Jan+01+2024&version=202209.1.0&consentId=test&interactionCount=1&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1",
     "domain": ".se.com", "path": "/"},
]

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        await ctx.add_cookies(CONSENT_COOKIES)
        page = await ctx.new_page()

        # Intercept JS files to search for patterns
        js_content = {}
        async def on_response(r):
            ct = r.headers.get("content-type", "")
            if "javascript" in ct and "svelte_app" in r.url:
                try:
                    text = await r.text()
                    js_content[r.url.split("/")[-1]] = text
                except:
                    pass

        page.on("response", on_response)
        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(6)

        # Look at page HTML for embedded data
        html = await page.content()
        print(f"HTML length: {len(html)} chars")

        # Look for IDs or API patterns in HTML
        id_patterns = re.findall(r'\b5[0-9]{5}\b', html)
        print(f"6-digit numbers in HTML: {len(id_patterns)} found, sample: {id_patterns[:10]}")

        # Look for API base URLs
        api_urls = re.findall(r'https?://[^"\'<>\s]+locate[^"\'<>\s]+', html)
        print(f"Locate URLs in HTML: {api_urls[:10]}")

        # Check if page shows partner list count
        partner_count = await page.evaluate("""
            (() => {
                // Look for count text
                const texts = Array.from(document.querySelectorAll('*'))
                    .filter(e => e.children.length === 0 && e.textContent.trim())
                    .map(e => e.textContent.trim())
                    .filter(t => /\d{3,4}/.test(t) && t.length < 50);
                return texts.slice(0, 20);
            })()
        """)
        print(f"\nNumbers on page: {partner_count}")

        # Look at JS files for the search pattern
        print(f"\nCaptured {len(js_content)} JS files")
        for fname, content in js_content.items():
            # Look for the search/ID-list patterns
            # Find where the 10 hardcoded IDs might come from
            patterns_found = []
            for pattern in [
                r'id-list',
                r'countryCode',
                r'pageSize',
                r'partnerIds',
                r'configurationId',
                r'globalSearch',
                r'searchPartners',
                r'getAllPartners',
                r'fetchPartners',
                r'loadMore',
                r'showMore',
                r'/api/partners',
                r'522837',  # one of the hardcoded IDs
            ]:
                if re.search(pattern, content):
                    idx = content.find(pattern.replace(r'/', '')) if '/' not in pattern else content.find(pattern[1:])
                    if idx >= 0:
                        ctx_snip = content[max(0,idx-100):idx+200]
                        patterns_found.append(f"  [{pattern}]: ...{ctx_snip[:200]}...")
            if patterns_found:
                print(f"\n{fname}:")
                for pf in patterns_found:
                    print(pf[:300])

        await browser.close()

asyncio.run(main())

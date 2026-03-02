"""
Test the /partners/all endpoint with various country codes.
Also figure out what headers make id-list-grouped return data from JS.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

# Key countries in SE's distributor network
COUNTRY_CODES = [
    "ww","gb","de","fr","us","se","dk","no","fi","pl","es","it","nl","be","ch",
    "at","pt","cz","sk","hu","ro","bg","hr","si","lt","lv","ee","gr","tr","ru",
    "ua","by","in","cn","jp","kr","au","nz","br","mx","ar","cl","co","za","ng",
    "eg","ma","ae","sa","qa","kw","il","sg","my","th","id","ph","vn","pk","bn",
    "ca","hk","tw","ba","rs","mk","al","me","md","ge","am","az","kz","uz","mn",
]

async def jfetch_full(page, url):
    return await page.evaluate(f"""
        fetch('{url}', {{headers: {{'Accept': 'application/json'}}}})
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

        # Intercept the initial page load to capture the working URL headers
        first_response_headers = {}
        async def on_response(r):
            nonlocal first_response_headers
            if "id-list-grouped" in r.url and r.status == 200:
                first_response_headers = dict(r.request.headers)
        page.on("response", on_response)

        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        print("Request headers from initial load:")
        for k, v in list(first_response_headers.items())[:15]:
            print(f"  {k}: {v[:80]}")

        # Dismiss cookie consent
        for sel in ["#onetrust-accept-btn-handler"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except:
                pass

        # Test /all endpoint with country codes
        print("\n=== /partners/all endpoint by country ===")
        results = {}
        for cc in COUNTRY_CODES[:20]:  # test first 20
            url = f"/ww/en/locate/api/partners/all?configurationId=221&languageCode=en&countryCode={cc}"
            r = await jfetch_full(page, url)
            status = r.get('status')
            body_text = r.get('body', '')
            try:
                body = json.loads(body_text)
                if isinstance(body, list):
                    n = len(body)
                    results[cc] = body
                    print(f"  cc={cc:>4}: [{n:>5}] records")
                else:
                    print(f"  cc={cc:>4}: HTTP{status} {str(body)[:80]}")
            except:
                print(f"  cc={cc:>4}: HTTP{status} {body_text[:80]}")

        # Also try with pageSize param
        print("\n=== /all with ww + pagination test ===")
        for extra in ["&pageSize=50", "&pageSize=100", "&pageSize=50&pageNumber=1", "&pageSize=50&pageNumber=2"]:
            url = f"/ww/en/locate/api/partners/all?configurationId=221&languageCode=en&countryCode=ww{extra}"
            r = await jfetch_full(page, url)
            status = r.get('status')
            try:
                body = json.loads(r.get('body', ''))
                n = len(body) if isinstance(body, list) else body
                print(f"  {extra}: HTTP{status} → {n}")
            except:
                print(f"  {extra}: HTTP{status} {r.get('body','')[:80]}")

        await browser.close()

        if results:
            total = sum(len(v) for v in results.values())
            print(f"\nTotal records collected: {total} across {len(results)} countries")
            # Save sample
            with open("/home/powerq001/getVendors/sample_all.json", "w") as f:
                json.dump({"results": results}, f, indent=2)

asyncio.run(main())

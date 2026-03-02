"""
Use Playwright to make authenticated in-page fetch() calls to the SE API,
iterating over ISO country codes to collect all distributors.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

# ISO 3166-1 alpha-2 codes that SE operates in
# This is a broad list; codes that return 0 results are just skipped
COUNTRY_CODES = [
    "af","al","dz","ad","ao","ar","am","au","at","az",
    "bh","bd","by","be","bz","bj","bo","ba","bw","br",
    "bn","bg","bf","bi","kh","cm","ca","cv","cf","td",
    "cl","cn","co","cg","cd","cr","ci","hr","cu","cy",
    "cz","dk","dj","do","ec","eg","sv","ee","et","fi",
    "fr","ga","ge","de","gh","gr","gt","gn","hn","hk",
    "hu","in","id","ir","iq","ie","il","it","jm","jp",
    "jo","kz","ke","kw","kg","la","lv","lb","ly","lt",
    "lu","mk","mg","mw","my","mv","ml","mt","mr","mx",
    "md","mc","mn","me","ma","mz","na","np","nl","nz",
    "ni","ne","ng","no","om","pk","pa","pg","py","pe",
    "ph","pl","pt","pr","qa","ro","ru","rw","sa","sn",
    "rs","sg","sk","si","za","es","lk","se","ch","tw",
    "tz","th","tg","tn","tr","ug","ua","ae","gb","us",
    "uy","uz","ve","vn","ye","zm","zw","hk","mo","kw",
    "bh","om","qa","jo","il","tn","dz","ma","eg","ly",
]

# Deduplicate
COUNTRY_CODES = list(dict.fromkeys(COUNTRY_CODES))

BASE_API = "/ww/en/locate/api/partners/id-list-grouped"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        print("Loading page to establish session …")
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)

        # Dismiss cookie consent
        for sel in ["#onetrust-accept-btn-handler", "button[id*=accept]"]:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except:
                pass

        # First, fetch analytics to see what info is available
        analytics = await page.evaluate("""
            fetch('/ww/en/locate/api/configurations/221/analytics?cc=ww&lc=en')
                .then(r => r.json())
                .catch(e => ({error: e.toString()}))
        """)
        print("Analytics:", json.dumps(analytics, indent=2)[:1000])

        # Try fetching with a sample country code via in-page fetch
        test_cc = "gb"
        test_result = await page.evaluate(f"""
            fetch('{BASE_API}?configurationId=221&languageCode=en&countryCode={test_cc}&ts=' + Date.now())
                .then(r => r.json())
                .catch(e => ({{error: e.toString()}}))
        """)
        if isinstance(test_result, list):
            print(f"\ncountryCode={test_cc}: {len(test_result)} records")
            if test_result:
                print("Sample:", json.dumps(test_result[0], indent=2)[:300])
        else:
            print(f"\ncountryCode={test_cc}:", test_result)

        # Also test 'all' or wildcard
        for special in ["*", "all", "ALL", "WW", "ww", ""]:
            try:
                r = await page.evaluate(f"""
                    fetch('{BASE_API}?configurationId=221&languageCode=en&countryCode={special}&ts=' + Date.now())
                        .then(r => r.json())
                        .catch(e => ({{error: e.toString()}}))
                """)
                n = len(r) if isinstance(r, list) else str(r)[:80]
                print(f"countryCode={special!r}: {n} records")
            except Exception as e:
                print(f"countryCode={special!r}: error {e}")

        await browser.close()

asyncio.run(main())

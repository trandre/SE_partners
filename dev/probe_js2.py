"""
Use Playwright to fetch the Svelte app JS (bypasses Akamai 403),
then grep for API patterns and pagination keywords.
"""
import asyncio, re
from playwright.async_api import async_playwright

SVELTE_BASE = "https://www.se.com/us/en/locate/_svelte_app/immutable"

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

        # First load the main page to establish session
        print("Loading main page …")
        await page.goto(
            "https://www.se.com/ww/en/locate/"
            "221-find-an-industrial-automation-distributor-near-you",
            wait_until="domcontentloaded", timeout=60000
        )
        await asyncio.sleep(3)

        # Get list of JS files from page
        js_srcs = await page.evaluate("""
            Array.from(document.querySelectorAll('script[src]'))
                 .map(s => s.src)
                 .filter(s => s.includes('_svelte_app'))
        """)
        print(f"Found {len(js_srcs)} Svelte JS files")

        api_patterns = set()
        param_keys   = set()

        for src_url in js_srcs[:10]:
            print(f"Fetching {src_url[-60:]} …")
            try:
                content = await page.evaluate(f"""
                    fetch('{src_url}').then(r => r.text())
                """)
                # Look for API paths
                paths = re.findall(
                    r"""['"](/[^'"]*api[^'"]{0,120}|[^'"]*partners[^'"]{0,120})['"]""",
                    content
                )
                params = re.findall(
                    r"""['"]([a-zA-Z][a-zA-Z0-9_]*(?:[Pp]age|[Oo]ffset|[Cc]ount|[Ll]imit|[Ss]ize|[Nn]umber|[Ss]tart)[a-zA-Z0-9_]*)['"]""",
                    content
                )
                api_patterns.update(p for p in paths if len(p) < 150)
                param_keys.update(params)
            except Exception as e:
                print(f"  Error: {e}")

        await browser.close()

    print("\n=== API Paths found ===")
    for p in sorted(api_patterns):
        if "locate" in p or "partner" in p or "distributor" in p:
            print(f"  {p}")

    print("\n=== Pagination keys found ===")
    for k in sorted(param_keys):
        print(f"  {k}")

asyncio.run(main())

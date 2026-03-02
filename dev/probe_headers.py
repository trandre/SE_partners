"""
Capture the exact request/response headers for the successful id-list-grouped call.
Then replicate the request from JS fetch with those exact headers.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        req_info = {}

        async def on_request(req):
            if "id-list-grouped" in req.url:
                req_info['url'] = req.url
                req_info['headers'] = dict(req.headers)
                req_info['method'] = req.method
                print(f"REQUEST: {req.method} {req.url}")
                for k, v in req.headers.items():
                    print(f"  {k}: {v[:100]}")

        async def on_response(r):
            if "id-list-grouped" in r.url:
                print(f"\nRESPONSE: {r.status} {r.url}")
                print(f"  Content-Type: {r.headers.get('content-type','')}")

        page.on("request", on_request)
        page.on("response", on_response)

        print("Loading page …")
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)

        if not req_info:
            print("No id-list-grouped request captured yet, waiting more...")
            await asyncio.sleep(5)

        if req_info:
            print(f"\nCaptured request headers: {list(req_info['headers'].keys())}")

            # Now try to replicate via JS fetch with the exact same headers
            headers_js = json.dumps(req_info['headers'])
            url = req_info['url']

            # Fresh ts
            url_fresh = url.split('&ts=')[0] + f"&ts=" + str(int(await page.evaluate("Date.now()")))

            result = await page.evaluate(f"""
                fetch('{url_fresh}', {{
                    method: 'GET',
                    headers: {headers_js}
                }}).then(async r => ({{status: r.status, body: await r.text()}}))
                  .catch(e => ({{error: e.toString()}}))
            """)
            print(f"\nReplicated fetch result: status={result.get('status')}")
            body_text = result.get('body', '')
            try:
                body = json.loads(body_text)
                print(f"  Body type: {type(body).__name__}, len: {len(body) if isinstance(body, list) else '?'}")
            except:
                print(f"  Body: {body_text[:200]}")

            # Try calling from outside the page using aiohttp
            print("\n=== aiohttp external request ===")
            import aiohttp
            cookies = {c['name']: c['value'] for c in await ctx.cookies()}
            print(f"Cookies: {list(cookies.keys())}")
            async with aiohttp.ClientSession(headers=req_info['headers']) as session:
                async with session.get(url_fresh, cookies=cookies) as r:
                    print(f"  Status: {r.status}")
                    text = await r.text()
                    try:
                        d = json.loads(text)
                        print(f"  Type: {type(d).__name__}, len: {len(d) if isinstance(d, list) else '?'}")
                        if isinstance(d, list) and d:
                            print(f"  Sample: {json.dumps(d[0])[:200]}")
                    except:
                        print(f"  Body: {text[:200]}")
        else:
            print("ERROR: No id-list-grouped request was captured!")

        await browser.close()

asyncio.run(main())

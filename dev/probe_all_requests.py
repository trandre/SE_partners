"""
Capture EVERY request/response during page load to find the ID-list source.
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
     "value": "isGpcEnabled=0&datestamp=Mon+Jan+01+2024+00%3A00%3A00&version=202209.1.0&isIABGlobal=false&consentId=test&interactionCount=1&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1",
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

        # Capture ALL requests with timing
        all_reqs = []
        all_resps = []

        async def on_req(req):
            all_reqs.append({
                "t": asyncio.get_event_loop().time(),
                "method": req.method,
                "url": req.url[:200],
                "body": req.post_data,
            })

        async def on_resp(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                try:
                    d = await r.json()
                    all_resps.append({
                        "t": asyncio.get_event_loop().time(),
                        "status": r.status,
                        "url": r.url[:200],
                        "body": d,
                    })
                except:
                    pass

        page.on("request", on_req)
        page.on("response", on_resp)

        print("Loading page …")
        await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)

        print(f"Total requests: {len(all_reqs)}")
        print(f"JSON responses: {len(all_resps)}")

        print("\n=== ALL JSON RESPONSES ===")
        for r in all_resps:
            body = r["body"]
            if isinstance(body, list):
                print(f"  [{len(body):>5}]  HTTP{r['status']}  {r['url'][:120]}")
                if body and isinstance(body[0], int):
                    print(f"          → list of ints: {body[:10]}...")
                elif body and isinstance(body[0], dict):
                    print(f"          → list of dicts, keys={list(body[0].keys())[:5]}")
            elif isinstance(body, dict):
                keys = list(body.keys())[:6]
                # Check for ID lists
                for k, v in body.items():
                    if isinstance(v, list) and len(v) > 50 and isinstance(v[0], int):
                        print(f"  [IDs!]  HTTP{r['status']}  {r['url'][:120]}")
                        print(f"          → {k}: [{len(v)} ints] {v[:5]}...")
                print(f"  [dict:{keys}]  HTTP{r['status']}  {r['url'][:120]}")

        print("\n=== ALL REQUESTS (sorted by time, API only) ===")
        t0 = all_reqs[0]["t"] if all_reqs else 0
        for req in all_reqs:
            if any(kw in req["url"] for kw in ["locate", "partner", "distributor", "api.se.com"]):
                dt = req["t"] - t0
                body = (req["body"] or "")[:100]
                print(f"  +{dt:5.1f}s  {req['method']:4}  {req['url'][:130]}  {body}")

        # Also check if the 10 hardcoded IDs appear anywhere in the JS
        ids_to_check = [522837, 387749, 551787]
        print(f"\n=== Checking if IDs {ids_to_check} appear in inline scripts ===")
        inline_scripts = await page.evaluate("""
            Array.from(document.querySelectorAll('script:not([src])'))
                .map(s => s.textContent)
                .filter(t => t.length > 0)
        """)
        for script in inline_scripts:
            for id_ in ids_to_check:
                if str(id_) in script:
                    idx = script.index(str(id_))
                    print(f"  ID {id_} found in inline script: ...{script[max(0,idx-50):idx+100]}...")

        await browser.close()

asyncio.run(main())

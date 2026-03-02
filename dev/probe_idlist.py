"""
Find the endpoint that returns ALL partner IDs.
The page first fetches IDs, then POSTs them to id-list-grouped for full details.
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

        all_requests = []
        async def on_request(req):
            all_requests.append({
                "method": req.method,
                "url": req.url,
                "body": req.post_data,
            })

        all_responses = []
        async def on_response(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                try:
                    d = await r.json()
                    all_responses.append({"url": r.url, "status": r.status, "body": d})
                except:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)

        # Show ALL requests made
        print("=== ALL REQUESTS (se.com only) ===")
        for req in all_requests:
            if "se.com" in req["url"]:
                body_preview = req["body"][:60] if req["body"] else ""
                print(f"  {req['method']:4} {req['url'][:130]} {body_preview}")

        # Show all JSON responses from se.com
        print("\n=== ALL JSON RESPONSES (se.com only) ===")
        for r in all_responses:
            if "se.com" in r["url"]:
                body = r["body"]
                if isinstance(body, list):
                    print(f"  [{len(body):>5}] HTTP{r['status']} {r['url'][:120]}")
                    if body and isinstance(body[0], int):
                        print(f"         → List of integers (IDs?): {body[:10]}")
                elif isinstance(body, dict):
                    keys = list(body.keys())[:5]
                    print(f"  [dict:{keys}] HTTP{r['status']} {r['url'][:100]}")
                    if any(k for k in ("total", "count", "ids", "partnerIds") if k in body):
                        print(f"         → {body}")

        await browser.close()

asyncio.run(main())

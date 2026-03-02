"""
Trigger a country search on the SE locator page and capture the
ID-list API call that returns all partner IDs for that country.
"""
import asyncio, json
from playwright.async_api import async_playwright

TARGET = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-web-security", "--no-sandbox"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await ctx.new_page()

        api_log = []
        async def on_request(req):
            if "se.com" in req.url and ("locate" in req.url or "partner" in req.url.lower()):
                api_log.append({
                    "method": req.method,
                    "url": req.url,
                    "body": req.post_data,
                })

        page.on("request", on_request)

        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # Force-remove cookie overlays via JS
        await page.evaluate("""
            document.querySelectorAll(
                '#onetrust-consent-sdk, .onetrust-pc-dark-filter, #onetrust-policy, .onetrust-banner-sdk'
            ).forEach(e => e.remove());
            document.body.style.overflow = 'auto';
        """)
        await asyncio.sleep(0.5)

        # Accept via button if still present
        for sel in [
            "#onetrust-accept-btn-handler",
            "button[id*=accept]",
            "#accept-recommended-btn-handler",
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click(force=True)
                    print(f"Accepted cookies via: {sel}")
                    await asyncio.sleep(1)
                    break
            except:
                pass

        # Remove overlay again after click
        await page.evaluate("""
            document.querySelectorAll(
                '#onetrust-consent-sdk, .onetrust-pc-dark-filter'
            ).forEach(e => e.remove());
        """)
        await asyncio.sleep(0.5)

        # Find the country search input and interact
        inp = await page.query_selector('input[placeholder="Search country"]')
        if not inp:
            # Try broader selector
            for sel in ['input.ploc-w-full', 'input[class*="ploc"]', 'input']:
                inps = await page.query_selector_all(sel)
                for candidate in inps:
                    ph = await candidate.get_attribute("placeholder") or ""
                    if "country" in ph.lower() or "search" in ph.lower():
                        inp = candidate
                        print(f"Found input via {sel}: placeholder={ph!r}")
                        break
                if inp:
                    break

        if inp:
            print("Clicking country search input …")
            await inp.click(force=True, timeout=5000)
            await asyncio.sleep(1)
            await inp.fill("United Kingdom")
            await asyncio.sleep(3)

            # Dump what's visible on page
            dropdown_items = await page.evaluate("""
                (() => {
                    const items = [];
                    for (const sel of ['li', '[role=option]', '[role=listbox] *', '.dropdown li', '[class*=list] li', '[class*=option]']) {
                        document.querySelectorAll(sel).forEach(el => {
                            const txt = el.textContent.trim();
                            if (txt && txt.length < 100 && el.offsetHeight > 0) {
                                items.push({tag: el.tagName, text: txt, class: el.className.substring(0,50)});
                            }
                        });
                    }
                    return [...new Map(items.map(i => [i.text, i])).values()].slice(0, 15);
                })()
            """)
            print(f"Dropdown items: {dropdown_items}")

            # Try pressing Enter or clicking first result
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            await asyncio.sleep(5)

            print(f"\nAPI calls after country select ({len(api_log)} total):")
            for req in api_log:
                body_preview = (req["body"] or "")[:100]
                print(f"  {req['method']:4} {req['url'][:130]} {body_preview}")
        else:
            print("ERROR: Could not find country search input")
            # Dump all visible inputs
            all_inputs = await page.evaluate("""
                Array.from(document.querySelectorAll('input')).slice(0,10).map(i => ({
                    ph: i.placeholder, name: i.name, type: i.type, visible: i.offsetHeight > 0,
                    cls: i.className.substring(0, 60)
                }))
            """)
            print("All inputs:", all_inputs)

        await browser.close()

asyncio.run(main())

# Lessons Learned & Failures to Avoid

This document captures every significant obstacle hit during development of the
SE Partner Scraper, why it happened, and how to avoid it in future scrapers.

---

## 1. Akamai Blocked All Direct HTTP Requests

**What happened:**
Every `requests` or `aiohttp` call to `se.com` returned HTTP 404 or a Akamai
bot-challenge page, even with a realistic `User-Agent` header.

**Why:**
Akamai's Bot Manager fingerprints requests using TLS fingerprinting (JA3/JA3S),
HTTP/2 settings negotiation, and JavaScript challenge evaluation. A plain
Python HTTP client fails all three checks before the server even reads your
headers.

**Fix:**
Make all API calls from inside a live Playwright browser context via
`page.evaluate("fetch(...)")`. The browser passes Akamai's challenge because it
has a genuine TLS fingerprint and executes the JavaScript challenge in-page.

**Rule going forward:**
Before writing a single HTTP call, check whether the target uses Akamai, Cloudflare,
or DataDome. If yes, plan for a browser-based fetch strategy from the start.
Tools like `curl -I <url>` and inspecting response headers (`cf-ray`, `x-check-cacheable`,
`Server: AkamaiGHost`) reveal which WAF is in use.

---

## 2. Cookie Consent Modal Blocked All Page Interaction

**What happened:**
The OneTrust cookie consent modal intercepted every pointer event — no button,
map, or list item could be clicked.

**Why:**
OneTrust renders an overlay with `z-index: 2147483647` (max possible) and a
transparent `pointer-events: all` div that captures every click before it
reaches the underlying page.

**Attempts that failed:**
- `page.click("button#accept-all")` — element not found due to iframe nesting
- `page.evaluate("document.getElementById('onetrust-banner-sdk').remove()")` —
  the element was re-injected after removal by the Svelte app's lifecycle hooks
- Waiting for the button to become stable and re-clicking — always intercepted

**Fix:**
Pre-set the `OptanonConsent` and `OptanonAlertBoxClosed` cookies via
`ctx.add_cookies()` *before* the page loads. OneTrust reads these cookies on
initialization and skips rendering the modal entirely.

```python
await ctx.add_cookies([
    {"name": "OptanonAlertBoxClosed", "value": "2024-01-01T00:00:00.000Z", ...},
    {"name": "OptanonConsent", "value": "...groups=C0001%3A1%2CC0002%3A1...", ...},
])
```

**Rule going forward:**
For any OneTrust-protected site, inspect the cookies set after manually clicking
"Accept All" in your browser DevTools → Application → Cookies. Copy those exact
values into `CONSENT_COOKIES`. Never try to click the modal programmatically.

---

## 3. Wrong Parameter Name for the Locations Endpoint

**What happened:**
`GET /api/partners/locations?configurationId=221` returned HTTP 400:
`"Required parameter 'config' is not present."`

**Why:**
The SE Partner Locator app exposes two distinct endpoints with different parameter
schemas:
- `/locations` uses the legacy short param `config=221`
- `/id-list-grouped` uses the newer full param `configurationId=221`

Because both endpoints deal with the same configuration ID 221, it was natural
(and wrong) to assume they'd share parameter names.

**Fix:**
Use `config=221` for `/locations` and `configurationId=221` for `/id-list-grouped`.
This was discovered by intercepting the exact requests the Svelte app itself made
to the API (`page.on("request", ...)`) rather than guessing.

**Rule going forward:**
When an endpoint returns 400 "missing parameter", don't guess parameter names.
Intercept the real traffic the JavaScript app sends using `page.on("request")`
and copy the exact query string character-for-character.

---

## 4. Mistaking a POST Endpoint for a GET Endpoint

**What happened:**
`GET /api/partners/id-list-grouped?configurationId=221&...` returned 404. Spent
time testing different query parameters before realizing this endpoint only
accepts POST.

**Why:**
REST naming conventions were not followed. "id-list-grouped" sounds like a read
operation; intuition says GET. But the app sends a body `{"ids": [...50 IDs...]}`
which requires POST.

**Fix:**
Intercept the actual app requests with `page.on("request", ...)` and log both
the HTTP method and the request body:

```python
async def on_req(req):
    if "id-list-grouped" in req.url:
        print(req.method, req.url)
        print(await req.body())
page.on("request", on_req)
```

**Rule going forward:**
When probing an unknown API, always capture method + URL + body together. Never
assume a data-retrieval endpoint uses GET.

---

## 5. Only 10 Records Scraped on the First Run

**What happened:**
The first working scraper returned exactly 10 rows — the same 10 "featured"
distributors shown in the default page view worldwide.

**Why:**
The initial approach intercepted XHR requests and replayed the POST body it saw.
The Svelte app hardcodes 10 globally-featured partner IDs for the initial
worldwide view. The app only fetches region-specific results after a map
interaction (pan/zoom), which the automated browser never triggered.

**Fix:**
Use the two-step strategy instead of intercepting the initial page load:
1. `GET /locations?config=221&...` → returns all 3,387 IDs + coordinates
2. Batch `POST /id-list-grouped` with those IDs → returns full details

**Rule going forward:**
When a page shows a "featured" or "near you" default view, the initial API
response is never the full dataset. Inspect the network tab for a separate
"get all" or "get list" endpoint that feeds the map/list data model.

---

## 6. Permission Denied on the Target Directory

**What happened:**
The original target directory `/opt/getVendors/` was owned by root with no
write permissions for the `powerq001` user. Creating files there failed silently
in some tools and noisily in others.

**Fix:**
Use `$HOME` for all development work. Reserve `/opt/` for system-installed
production deployments managed by an admin.

**Rule going forward:**
Always `ls -la` the target directory before starting. If it's under `/opt/`,
`/usr/`, or `/etc/`, either request a sudo `chown` or redirect to `~/projects/`.

---

## 7. Selenium + System Chrome Dependency Not Met

**What happened:**
The original script used `selenium` + `chromedriver` + a system Chrome binary.
The machine had none of these installed, and installing system Chrome requires
root access.

**Fix:**
Switch to Playwright, which downloads its own self-contained Chromium binary
into `~/.cache/ms-playwright/` with no root access required:

```bash
pip install playwright
python -m playwright install chromium
```

**Rule going forward:**
Default to Playwright for all new browser automation. It owns its own browser
binary, supports async natively, and has better CDP (Chrome DevTools Protocol)
integration for request interception.

---

## 8. HTTP 500 on Specific Batches Due to Corrupted Backend Data

**What happened:**
Batches 65 and 66 consistently returned HTTP 500:
`{"code":"RUNTIME_EXCEPTION","message":"For input string: \" Procurement\""}`

**Why:**
Schneider Electric's backend has a corrupted `businessType` value (`" Procurement"`
with a leading space) for some partner records. Their API's parser throws a Java
`NumberFormatException` when it tries to cast this to an integer.

**Fix:**
Added exponential-backoff retry logic (3 attempts, 2s/4s/8s). Since the failure
is data-driven (not transient), retries always fail for these specific batches —
but the retry logic is still correct and essential for genuine transient failures
(network blips, temporary rate limiting).

The affected ~100 partners cannot be retrieved until SE fixes their data.

**Rule going forward:**
Never treat HTTP 500 as a hard stop. Always retry with backoff. Log the skipped
IDs precisely so the data gap is auditable. Separate "server data error" (cannot
fix) from "transient server error" (retry will work) in your logging.

---

## 9. Assuming `countryCode=ww` Returns Worldwide Results

**What happened:**
Initial probes omitted `countryCode` entirely or used specific country codes
(e.g., `countryCode=se`), which returned only a subset of partners.

**Why:**
The app uses `ww` (Schneider Electric's internal code for "worldwide") as the
global aggregator. This is non-standard — ISO 3166-1 does not include `ww`.

**Fix:**
Always include `countryCode=ww` in requests to retrieve all partners globally.

**Rule going forward:**
Check the actual requests the app makes to find non-standard "all countries"
codes. Do not rely on ISO standards for proprietary API parameters.

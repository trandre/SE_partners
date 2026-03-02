#!/usr/bin/env python3
"""
Schneider Electric Partner Locator — Multi-Agent Async Scraper  (v2)
====================================================================
Reverse-engineered API flow:
  1.  GET  /api/partners/locations?config=221&languageCode=en&countryCode=ww
      → returns JSON array with ALL 3387+ partner IDs + coordinates

  2.  POST /api/partners/id-list-grouped?configurationId=221&...
      Body: {"ids": [id1, id2, ...50...]}
      → returns full partner details (all nested fields)

Three async agents run concurrently via asyncio.gather():
  BrowserAgent   – Playwright loads page (for Akamai session),
                   fetches all IDs via GET /locations, then fans-out
                   concurrent batch POSTs via the live browser context.
  ParserAgent    – Flattens every nested field into one flat dict per partner.
  WriterAgent    – Deduplicates on the fly, writes CSV, runs QA report.
"""

import asyncio
import csv
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

# ─── Paths ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
TS        = datetime.now().strftime("%Y%m%d_%H%M%S")
CLEAN_CSV = OUTPUT_DIR / f"distributors_{TS}.csv"
RAW_JSONL = OUTPUT_DIR / f"raw_responses_{TS}.jsonl"
LOG_FILE  = OUTPUT_DIR / f"scraper_{TS}.log"

# ─── API config ───────────────────────────────────────────────────────────────
SE_BASE       = "https://www.se.com"
LOCATOR_PAGE  = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)
LOCATIONS_URL = (
    "/ww/en/locate/api/partners/locations"
    "?config=221&languageCode=en&countryCode=ww"
)
DETAILS_PATH  = "/ww/en/locate/api/partners/id-list-grouped"
DETAILS_PARAMS= "configurationId=221&languageCode=en&countryCode=ww"

POST_BATCH_SIZE  = 50     # IDs per POST to id-list-grouped
CONCURRENT_POSTS = 6      # parallel POST requests at once
BATCH_DELAY      = 0.4    # seconds between batches (rate-limit courtesy)
PAGE_LOAD_WAIT   = 6      # seconds after page load before API calls

# Cookie consent cookies (bypass the modal without needing any click)
CONSENT_COOKIES = [
    {"name": "OptanonAlertBoxClosed", "value": "2024-01-01T00:00:00.000Z",
     "domain": ".se.com", "path": "/"},
    {"name": "OptanonConsent",
     "value": (
         "isGpcEnabled=0&datestamp=Mon+Jan+01+2024&version=202209.1.0"
         "&consentId=consent-bypass&interactionCount=1"
         "&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1"
     ),
     "domain": ".se.com", "path": "/"},
]

_DONE = object()   # end-of-stream sentinel

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(name)s]  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
def _log(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ══════════════════════════════════════════════════════════════════════════════
# DATA EXTRACTION — full nested-field flattening
# ══════════════════════════════════════════════════════════════════════════════

COLUMN_ORDER: list[str] = [
    # Identity
    "id", "accountBfoId", "idGroup",
    # Company
    "companyName",
    # Address
    "address1", "address2", "city", "zipCode",
    "administrativeRegion", "stateId",
    "country", "countryId",
    # Geo
    "latitude", "longitude",
    # Web & logo
    "webSite", "webSite2", "logoUrl",
    # Contact (from partnerDetails.partnerContact)
    "contact_email", "contact_phone",
    # Person (from partnerDetails)
    "firstName", "lastName", "about", "description",
    # Flags
    "emailExists", "phoneExists", "eshop",
    "openingHoursType", "productCount",
    # Business type
    "businessType_codes", "businessType_names",
    # Program level (first entry)
    "programLevel_logoUrl", "programLevel_globalId",
    "programLevel_displayRank", "programLevel_b2cAvailable",
    # Usually-empty arrays
    "openingHours", "preferredMarketServe",
    "competence", "areaOfFocus", "customReference",
]


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    return str(v).strip()


def _clean(v: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", v).strip()


def extract_record(item: dict) -> dict:
    """Flatten one SE partner JSON object into a single flat dict."""
    row: dict = {}

    # Scalar top-level fields
    for f in (
        "accountBfoId", "id", "idGroup",
        "country", "companyName",
        "address1", "address2", "zipCode", "city",
        "webSite", "webSite2", "countryId",
        "latitude", "longitude",
        "administrativeRegion", "stateId",
        "emailExists", "phoneExists",
        "openingHoursType", "eshop",
        "productCount", "logoUrl",
    ):
        row[f] = _clean(_s(item.get(f)))

    # partnerDetails
    pd_data  = item.get("partnerDetails") or {}
    row["firstName"] = _clean(_s(pd_data.get("firstName")))
    row["lastName"]  = _clean(_s(pd_data.get("lastName")))
    row["about"]     = _clean(_s(pd_data.get("about")))
    contact = pd_data.get("partnerContact") or {}
    row["contact_email"] = _clean(_s(contact.get("email")))
    row["contact_phone"] = _clean(_s(contact.get("phone")))
    descs = pd_data.get("descriptions") or []
    row["description"] = _clean(next(
        (_s(d.get("description")) for d in descs
         if d.get("isDefault") and d.get("description")),
        ""
    ))

    # businessType[]
    bt_list = item.get("businessType") or []
    row["businessType_codes"] = "; ".join(
        _s(b.get("code")) for b in bt_list if b.get("code")
    )
    row["businessType_names"] = "; ".join(
        _s(b.get("name")) for b in bt_list if b.get("name")
    )

    # programLevels[] (first entry)
    pl_list = item.get("programLevels") or []
    pl = pl_list[0] if pl_list else {}
    row["programLevel_logoUrl"]     = _clean(_s(pl.get("logoUrl")))
    row["programLevel_globalId"]    = _clean(_s(pl.get("globalProgramLevelId")))
    row["programLevel_displayRank"] = _clean(_s(pl.get("displayRank")))
    row["programLevel_b2cAvailable"]= _clean(_s(pl.get("b2cAvailable")))

    # Usually-empty arrays
    for arr_f in (
        "openingHours", "preferredMarketServe",
        "competence", "areaOfFocus", "customReference",
    ):
        arr = item.get(arr_f) or []
        row[arr_f] = "; ".join(json.dumps(v, ensure_ascii=False) for v in arr)

    return row


def _partner_list(body) -> list:
    """Extract partner list from various JSON response shapes."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("items", "results", "data", "partners", "distributors",
                    "dealers", "content", "hits", "records", "list"):
            val = body.get(key)
            if isinstance(val, list) and val:
                return val
        if any(k in body for k in ("id", "companyName", "partnerName", "name")):
            return [body]
    return []


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1  —  BROWSER AGENT
# ══════════════════════════════════════════════════════════════════════════════

async def browser_agent(raw_queue: asyncio.Queue) -> None:
    log = _log("BrowserAgent")
    log.info("Starting …")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        # Pre-set consent cookies so the modal never appears
        await ctx.add_cookies(CONSENT_COOKIES)
        page = await ctx.new_page()

        log.info(f"Loading {LOCATOR_PAGE} …")
        await page.goto(LOCATOR_PAGE, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(PAGE_LOAD_WAIT)

        # ── Step 1: GET all partner IDs from /locations ───────────────────
        log.info("Fetching all partner IDs from /locations …")
        locs_raw = await page.evaluate(f"""
            fetch('{LOCATIONS_URL}', {{headers: {{"Accept": "application/json"}}}})
                .then(async r => ({{status: r.status, body: await r.text()}}))
                .catch(e => ({{error: e.toString()}}))
        """)
        locs_status = locs_raw.get("status")
        locs_body   = json.loads(locs_raw.get("body", "{}"))

        partner_locs = locs_body.get("partnerLocations", [])
        all_ids = [p["id"] for p in partner_locs if "id" in p]
        log.info(f"  → {len(all_ids)} partner IDs retrieved (HTTP {locs_status})")

        if not all_ids:
            log.error("Could not retrieve partner IDs from /locations endpoint!")
            await browser.close()
            raw_queue.put_nowait(_DONE)
            return

        # ── Step 2: Batch POST to /id-list-grouped for full details ──────
        batches = [all_ids[i:i + POST_BATCH_SIZE]
                   for i in range(0, len(all_ids), POST_BATCH_SIZE)]
        total_batches = len(batches)
        log.info(f"Fetching full details: {len(all_ids)} IDs in "
                 f"{total_batches} batches of {POST_BATCH_SIZE} …")

        ts = int(time.time() * 1000)
        details_url = (
            f"{DETAILS_PATH}?{DETAILS_PARAMS}&ts={ts}"
        )

        # Fan-out concurrent POSTs in groups of CONCURRENT_POSTS
        async def post_batch(batch_ids: list, batch_idx: int) -> None:
            body_js = json.dumps({"ids": batch_ids})
            result  = await page.evaluate(f"""
                fetch('{details_url}', {{
                    method: 'POST',
                    headers: {{
                        'Accept':       'application/json, text/plain, */*',
                        'Content-Type': 'application/json',
                    }},
                    body: '{body_js}'
                }}).then(async r => ({{status: r.status, body: await r.text()}}))
                  .catch(e => ({{error: e.toString()}}))
            """)
            status    = result.get("status")
            body_text = result.get("body", "")
            try:
                data = json.loads(body_text)
                partners = _partner_list(data)
                if partners:
                    await raw_queue.put({"url": details_url, "body": data})
                    log.info(
                        f"  Batch {batch_idx+1}/{total_batches} "
                        f"({len(batch_ids)} IDs) → {len(partners)} records "
                        f"[HTTP {status}]"
                    )
                else:
                    log.warning(f"  Batch {batch_idx+1}: no records, status={status}, "
                                f"body={body_text[:120]}")
            except Exception as e:
                log.warning(f"  Batch {batch_idx+1}: parse error {e}, body={body_text[:100]}")

        for group_start in range(0, total_batches, CONCURRENT_POSTS):
            group_end = min(group_start + CONCURRENT_POSTS, total_batches)
            tasks = [
                post_batch(batches[i], i)
                for i in range(group_start, group_end)
            ]
            await asyncio.gather(*tasks)
            if group_end < total_batches:
                await asyncio.sleep(BATCH_DELAY)

        await browser.close()

    raw_queue.put_nowait(_DONE)
    log.info("Finished.")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2  —  PARSER AGENT
# ══════════════════════════════════════════════════════════════════════════════

async def parser_agent(
    raw_queue: asyncio.Queue, clean_queue: asyncio.Queue
) -> None:
    log = _log("ParserAgent")
    log.info("Starting …")
    parsed_total = 0

    raw_file = open(RAW_JSONL, "w", encoding="utf-8")
    while True:
        item = await raw_queue.get()
        if item is _DONE:
            break
        raw_file.write(json.dumps(item, ensure_ascii=False) + "\n")
        raw_file.flush()

        records = _partner_list(item.get("body", item))
        for rec in records:
            if isinstance(rec, dict):
                await clean_queue.put(extract_record(rec))
                parsed_total += 1

    raw_file.close()
    clean_queue.put_nowait(_DONE)
    log.info(f"Finished. Records parsed: {parsed_total}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3  —  WRITER AGENT  +  QA BOT
# ══════════════════════════════════════════════════════════════════════════════

def _fp(row: dict) -> str:
    return "||".join([
        row.get("id", ""),
        row.get("companyName", ""),
        row.get("city", ""),
        row.get("country", ""),
    ]).lower()


def run_qa(df: pd.DataFrame) -> None:
    """
    QA Bot — validates the output CSV and prints a detailed quality report.
    Checks: fill rates, coordinate validity, duplicates, column coverage.
    """
    log = _log("QABot")
    log.info("Running quality validation …")

    sep = "=" * 64
    print(f"\n{sep}")
    print("  QA REPORT  —  Schneider Electric Partner Locator")
    print(sep)
    print(f"  Total rows      : {len(df):,}")
    print(f"  Total columns   : {len(df.columns)}")
    print(f"  CSV file        : {CLEAN_CSV.resolve()}")
    print(f"  Raw backup      : {RAW_JSONL.resolve()}")
    print(sep)

    # ── Column fill rates ────────────────────────────────────────────────
    print("\n  Column fill rates (% non-empty):")
    fill_rates = {}
    for col in df.columns:
        n = (df[col].astype(str).str.strip() != "").sum()
        fill_rates[col] = 100.0 * n / len(df) if len(df) else 0.0
    for col, pct in sorted(fill_rates.items(), key=lambda x: -x[1]):
        bar  = "#" * int(pct / 5)
        flag = "  ← LOW" if pct < 10 else ""
        print(f"    {col:<40s}  {pct:5.1f}%  {bar}{flag}")

    # ── Geo sanity ───────────────────────────────────────────────────────
    if "latitude" in df.columns and "longitude" in df.columns:
        bad_lat = pd.to_numeric(df["latitude"], errors="coerce").isna().sum()
        bad_lon = pd.to_numeric(df["longitude"], errors="coerce").isna().sum()
        print(f"\n  Bad latitude values  : {bad_lat}")
        print(f"  Bad longitude values : {bad_lon}")

    # ── Duplicate IDs ────────────────────────────────────────────────────
    if "id" in df.columns:
        dup = df["id"].duplicated().sum()
        print(f"  Duplicate IDs        : {dup}")

    # ── Country distribution ─────────────────────────────────────────────
    if "country" in df.columns:
        top = df["country"].value_counts().head(20)
        print("\n  Top 20 countries:")
        for country, cnt in top.items():
            print(f"    {country:<40s}  {cnt:>5,}")

    # ── Business type distribution ───────────────────────────────────────
    if "businessType_names" in df.columns:
        bt_exploded = (
            df["businessType_names"]
            .str.split("; ")
            .explode()
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
        )
        print("\n  Business type breakdown:")
        for bt, cnt in bt_exploded.items():
            print(f"    {bt:<45s}  {cnt:>5,}")

    # ── Sample rows ──────────────────────────────────────────────────────
    show_cols = [c for c in (
        "companyName", "city", "country",
        "contact_email", "contact_phone",
        "businessType_names",
    ) if c in df.columns]
    print(f"\n  First 3 rows ({', '.join(show_cols)}):")
    print(df[show_cols].head(3).to_string(index=False))
    print(f"\n{sep}\n")


async def writer_agent(clean_queue: asyncio.Queue) -> None:
    log = _log("WriterAgent")
    log.info("Starting …")

    all_rows: list[dict] = []
    seen:     set[str]   = set()

    while True:
        row = await clean_queue.get()
        if row is _DONE:
            break
        fp = _fp(row)
        if fp and fp in seen:
            continue
        if fp:
            seen.add(fp)
        all_rows.append(row)
        if len(all_rows) % 200 == 0:
            log.info(f"  Accumulated {len(all_rows):,} unique rows …")

    log.info(f"Queue drained. {len(all_rows):,} unique rows collected.")

    if not all_rows:
        log.error(
            "No data collected!\n"
            f"  Check: {RAW_JSONL}\n"
            "  The /locations endpoint may have changed."
        )
        return

    # Build final column list (known order + any extras)
    extra_cols = []
    all_seen_keys = {k for r in all_rows for k in r}
    for r in all_rows:
        for k in r:
            if k not in COLUMN_ORDER and k not in extra_cols:
                extra_cols.append(k)
    final_cols = [c for c in COLUMN_ORDER if c in all_seen_keys] + extra_cols

    df = pd.DataFrame(all_rows, columns=final_cols)
    df.replace("", pd.NA, inplace=True)
    df.dropna(axis=1, how="all", inplace=True)
    df.fillna("", inplace=True)

    df.to_csv(CLEAN_CSV, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")
    log.info(f"CSV written → {CLEAN_CSV.resolve()}  "
             f"({len(df):,} rows × {len(df.columns)} cols)")

    # Run QA validation
    run_qa(df)
    log.info("WriterAgent finished.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    log = _log("Main")
    log.info("=" * 64)
    log.info("SE Partner Locator Scraper  (3-Agent Async + QA Bot)")
    log.info(f"Output : {CLEAN_CSV}")
    log.info("=" * 64)

    raw_queue   = asyncio.Queue()
    clean_queue = asyncio.Queue()

    t0 = time.perf_counter()
    await asyncio.gather(
        browser_agent(raw_queue),
        parser_agent(raw_queue, clean_queue),
        writer_agent(clean_queue),
    )
    elapsed = time.perf_counter() - t0
    log.info(f"Total elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())

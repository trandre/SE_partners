"""
agents.py — The three async pipeline agents.

Pipeline:
    BrowserAgent  ->  raw_queue  ->  ParserAgent  ->  clean_queue  ->  WriterAgent

Usage::

    raw_q   = asyncio.Queue()
    clean_q = asyncio.Queue()
    cfg = RunConfig(csv_path=..., jsonl_path=...)
    await asyncio.gather(
        BrowserAgent(raw_q, cfg).run(),
        ParserAgent(raw_q, clean_q, cfg).run(),
        WriterAgent(clean_q, cfg).run(),
    )
"""

import asyncio
import csv
import json
import logging
import time
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

from .config import (
    BATCH_DELAY,
    CONCURRENT_POSTS,
    CONSENT_COOKIES,
    DETAILS_PARAMS,
    DETAILS_PATH,
    LOCATIONS_URL,
    LOCATOR_PAGE,
    MAX_BATCH_RETRIES,
    PAGE_LOAD_WAIT,
    POST_BATCH_SIZE,
    RETRY_BACKOFF,
    USER_AGENT,
    VIEWPORT,
)
from .extractor import COLUMN_ORDER, extract_record, partner_list_from_body
from .qa import run_qa

# Sentinel object placed on a queue to signal end-of-stream.
_DONE = object()


def _log(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ── Runtime configuration ─────────────────────────────────────────────────────


class RunConfig:
    """
    Holds per-run values injected from ``__main__.py``.

    All static defaults live in ``config.py``; this class holds only the
    values that can differ between runs (output paths, tuning overrides).

    Attributes:
        csv_path:    Destination path for the output CSV.
        jsonl_path:  Destination path for the raw JSONL backup.
        batch_size:  Number of IDs per POST batch.
        concurrency: Number of concurrent POST requests per group.
    """

    def __init__(
        self,
        csv_path: Path,
        jsonl_path: Path,
        batch_size: int = POST_BATCH_SIZE,
        concurrency: int = CONCURRENT_POSTS,
    ) -> None:
        self.csv_path    = csv_path
        self.jsonl_path  = jsonl_path
        self.batch_size  = batch_size
        self.concurrency = concurrency


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — BROWSER AGENT
# ══════════════════════════════════════════════════════════════════════════════


class BrowserAgent:
    """
    Uses Playwright (headless Chromium) to:

    1. Load the SE locator page (acquires Akamai session cookies).
    2. GET /locations → collect all partner IDs in one request.
    3. Batch POST to /id-list-grouped → push raw JSON batches onto raw_queue.

    All API calls are made from within the live browser context to bypass
    Akamai CDN protection, which blocks direct HTTP requests.
    """

    def __init__(self, raw_queue: asyncio.Queue, cfg: RunConfig) -> None:
        self._queue = raw_queue
        self._cfg   = cfg
        self._log   = _log("BrowserAgent")

    async def run(self) -> None:
        self._log.info("Starting ...")
        try:
            await self._execute()
        finally:
            # Always signal downstream even on an unhandled exception.
            self._queue.put_nowait(_DONE)
            self._log.info("Finished.")

    async def _execute(self) -> None:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                viewport=VIEWPORT,
            )
            await ctx.add_cookies(CONSENT_COOKIES)
            page = await ctx.new_page()

            self._log.info(f"Loading {LOCATOR_PAGE} ...")
            await page.goto(
                LOCATOR_PAGE, wait_until="domcontentloaded", timeout=60_000
            )
            await asyncio.sleep(PAGE_LOAD_WAIT)

            all_ids = await self._fetch_all_ids(page)
            if not all_ids:
                self._log.error(
                    "Could not retrieve partner IDs from /locations endpoint!"
                )
                await browser.close()
                return

            await self._fetch_all_details(page, all_ids)
            await browser.close()

    async def _fetch_all_ids(self, page) -> list[int]:
        """GET /locations and return the full list of partner IDs."""
        self._log.info("Fetching all partner IDs from /locations ...")
        locs_raw = await page.evaluate(f"""
            fetch('{LOCATIONS_URL}', {{headers: {{"Accept": "application/json"}}}})
                .then(async r => ({{status: r.status, body: await r.text()}}))
                .catch(e => ({{error: e.toString()}}))
        """)
        locs_status = locs_raw.get("status")
        try:
            locs_body = json.loads(locs_raw.get("body", "{}"))
        except json.JSONDecodeError:
            self._log.error(
                f"Failed to parse /locations response (HTTP {locs_status})"
            )
            return []

        partner_locs = locs_body.get("partnerLocations", [])
        all_ids = [p["id"] for p in partner_locs if "id" in p]
        self._log.info(
            f"  -> {len(all_ids)} partner IDs retrieved (HTTP {locs_status})"
        )
        return all_ids

    async def _fetch_all_details(self, page, all_ids: list[int]) -> None:
        """Fan out concurrent batch POSTs for full partner details."""
        ts = int(time.time() * 1000)
        details_url = f"{DETAILS_PATH}?{DETAILS_PARAMS}&ts={ts}"

        batches = [
            all_ids[i : i + self._cfg.batch_size]
            for i in range(0, len(all_ids), self._cfg.batch_size)
        ]
        total_batches = len(batches)
        self._log.info(
            f"Fetching full details: {len(all_ids)} IDs in "
            f"{total_batches} batches of {self._cfg.batch_size} ..."
        )

        for group_start in range(0, total_batches, self._cfg.concurrency):
            group_end = min(group_start + self._cfg.concurrency, total_batches)
            tasks = [
                self._post_batch_with_retry(
                    page, details_url, batches[i], i, total_batches
                )
                for i in range(group_start, group_end)
            ]
            await asyncio.gather(*tasks)
            if group_end < total_batches:
                await asyncio.sleep(BATCH_DELAY)

    async def _post_batch_with_retry(
        self,
        page,
        details_url: str,
        batch_ids: list,
        batch_idx: int,
        total_batches: int,
    ) -> None:
        """
        POST one batch to /id-list-grouped with exponential-backoff retry.

        Retries up to MAX_BATCH_RETRIES times on:
          - HTTP 500 (known issue on some batches due to malformed SE data)
          - JSON parse failure
          - JS-level network exception

        Backoff schedule: RETRY_BACKOFF * 2^(attempt-1) seconds per retry.
        """
        body_js = json.dumps({"ids": batch_ids})
        label   = f"Batch {batch_idx + 1}/{total_batches} ({len(batch_ids)} IDs)"

        for attempt in range(MAX_BATCH_RETRIES + 1):
            if attempt > 0:
                wait_secs = RETRY_BACKOFF * (2 ** (attempt - 1))
                self._log.warning(
                    f"  {label}: retry {attempt}/{MAX_BATCH_RETRIES} "
                    f"(waiting {wait_secs:.1f}s) ..."
                )
                await asyncio.sleep(wait_secs)

            result = await page.evaluate(f"""
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

            # JS-level network error (no HTTP status at all)
            if "error" in result and "status" not in result:
                self._log.warning(
                    f"  {label}: network error: {result['error']} "
                    f"(attempt {attempt + 1})"
                )
                continue

            # HTTP 500 — transient server-side failure
            if status == 500:
                self._log.warning(
                    f"  {label}: HTTP 500 (attempt {attempt + 1}), "
                    f"body={body_text[:120]}"
                )
                continue

            try:
                data = json.loads(body_text)
            except json.JSONDecodeError as exc:
                self._log.warning(
                    f"  {label}: JSON parse error (attempt {attempt + 1}): {exc}, "
                    f"body={body_text[:100]}"
                )
                continue

            partners = partner_list_from_body(data)
            if partners:
                await self._queue.put({"url": details_url, "body": data})
                self._log.info(
                    f"  {label} -> {len(partners)} records [HTTP {status}]"
                )
                return  # success — exit retry loop

            # HTTP 200 but empty — likely a legitimate API no-op; don't retry.
            self._log.warning(
                f"  {label}: no records in response, "
                f"status={status}, body={body_text[:120]}"
            )
            return

        self._log.error(
            f"  {label}: FAILED after {MAX_BATCH_RETRIES} retries. "
            f"First skipped IDs: {batch_ids[:5]} ..."
        )


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — PARSER AGENT
# ══════════════════════════════════════════════════════════════════════════════


class ParserAgent:
    """
    Consumes raw JSON batches from ``raw_queue``.

    For each batch:
      - Writes the raw JSON to the JSONL backup file.
      - Calls :func:`extract_record` on every partner object.
      - Pushes flat dicts onto ``clean_queue`` for the writer.
    """

    def __init__(
        self,
        raw_queue: asyncio.Queue,
        clean_queue: asyncio.Queue,
        cfg: RunConfig,
    ) -> None:
        self._raw   = raw_queue
        self._clean = clean_queue
        self._cfg   = cfg
        self._log   = _log("ParserAgent")

    async def run(self) -> None:
        self._log.info("Starting ...")
        parsed_total = 0

        with open(self._cfg.jsonl_path, "w", encoding="utf-8") as raw_file:
            while True:
                item = await self._raw.get()
                if item is _DONE:
                    break

                raw_file.write(json.dumps(item, ensure_ascii=False) + "\n")
                raw_file.flush()

                records = partner_list_from_body(item.get("body", item))
                for rec in records:
                    if isinstance(rec, dict):
                        await self._clean.put(extract_record(rec))
                        parsed_total += 1

        self._clean.put_nowait(_DONE)
        self._log.info(f"Finished. Records parsed: {parsed_total}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — WRITER AGENT
# ══════════════════════════════════════════════════════════════════════════════


def _fingerprint(row: dict) -> str:
    """Composite deduplication key: id||companyName||city||country (lowercased)."""
    return "||".join([
        row.get("id", ""),
        row.get("companyName", ""),
        row.get("city", ""),
        row.get("country", ""),
    ]).lower()


class WriterAgent:
    """
    Consumes flat partner dicts from ``clean_queue``.

    On queue drain:
      - Deduplicates rows by fingerprint.
      - Builds a pandas DataFrame with the canonical column order.
      - Writes the CSV file.
      - Triggers the QA report.
    """

    def __init__(self, clean_queue: asyncio.Queue, cfg: RunConfig) -> None:
        self._queue = clean_queue
        self._cfg   = cfg
        self._log   = _log("WriterAgent")

    async def run(self) -> None:
        self._log.info("Starting ...")

        all_rows: list[dict] = []
        seen: set[str] = set()

        while True:
            row = await self._queue.get()
            if row is _DONE:
                break
            fp = _fingerprint(row)
            if fp and fp in seen:
                continue
            if fp:
                seen.add(fp)
            all_rows.append(row)
            if len(all_rows) % 200 == 0:
                self._log.info(f"  Accumulated {len(all_rows):,} unique rows ...")

        self._log.info(f"Queue drained. {len(all_rows):,} unique rows collected.")

        if not all_rows:
            self._log.error(
                "No data collected!\n"
                f"  Check: {self._cfg.jsonl_path}\n"
                "  The /locations endpoint may have changed."
            )
            return

        self._write_csv(all_rows)
        self._log.info("WriterAgent finished.")

    def _write_csv(self, all_rows: list[dict]) -> None:
        """Build the final DataFrame, write CSV, and run QA."""
        all_seen_keys = {k for r in all_rows for k in r}
        extra_cols: list[str] = []
        for r in all_rows:
            for k in r:
                if k not in COLUMN_ORDER and k not in extra_cols:
                    extra_cols.append(k)
        final_cols = [c for c in COLUMN_ORDER if c in all_seen_keys] + extra_cols

        df = pd.DataFrame(all_rows, columns=final_cols)
        df.replace("", pd.NA, inplace=True)
        df.dropna(axis=1, how="all", inplace=True)
        df.fillna("", inplace=True)

        df.to_csv(
            self._cfg.csv_path,
            index=False,
            quoting=csv.QUOTE_ALL,
            encoding="utf-8-sig",
        )
        self._log.info(
            f"CSV written -> {self._cfg.csv_path.resolve()}  "
            f"({len(df):,} rows x {len(df.columns)} cols)"
        )
        run_qa(df, self._cfg.csv_path, self._cfg.jsonl_path)

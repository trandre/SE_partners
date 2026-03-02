# SE Partner Scraper

Async web scraper for the [Schneider Electric Partner Locator](https://www.se.com/ww/en/locate/221-find-an-industrial-automation-distributor-near-you).
Fetches all ~3,387 partner/distributor records via their internal API, using
Playwright (headless Chromium) to bypass Akamai CDN protection.

## Output

| File | Description |
|------|-------------|
| `output/distributors_YYYYMMDD_HHMMSS.csv` | Clean, deduplicated CSV (UTF-8 BOM, 36 columns) |
| `output/raw_responses_YYYYMMDD_HHMMSS.jsonl` | Raw API response backup (one batch per line) |
| `output/scraper_YYYYMMDD_HHMMSS.log` | Full run log |

## Quick Start

```bash
bash run.sh
```

This creates a `.venv/`, installs dependencies, downloads Playwright's bundled
Chromium (~150 MB, one-time), and runs the scraper. Completes in ~60 seconds.

## Manual Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
# or, for development (includes pytest):
pip install -e ".[dev]"

python -m playwright install chromium
```

## Usage

```bash
# Default run — output goes to ./output/
python -m se_scraper

# Custom output directory
python -m se_scraper --output-dir /data/se_output

# Reduce batch size and concurrency (useful on slow connections)
python -m se_scraper --batch-size 25 --concurrency 3

# Show all options
python -m se_scraper --help
```

## Package Structure

```
se_scraper/
├── __init__.py     Package metadata (__version__)
├── __main__.py     CLI entry point (argparse, logging setup, asyncio.run)
├── config.py       All constants: URLs, batch sizes, timeouts, cookies
├── extractor.py    Pure data flattening: extract_record(), _s(), _clean()
├── agents.py       BrowserAgent, ParserAgent, WriterAgent (async classes)
└── qa.py           QA report: run_qa()

tests/
└── test_extractor.py   ~25 unit tests — no network access required

dev/
└── probe_*.py          API investigation scripts (kept for reference)
```

## Running Tests

```bash
pytest tests/ -v
```

All tests in `tests/test_extractor.py` cover the pure data-extraction logic
and run without any network access.

## API Flow

```
GET  /ww/en/locate/api/partners/locations?config=221&languageCode=en&countryCode=ww
     -> JSON: {partnerLocations: [{id, latitude, longitude, countryId}, ...]}
        (~3,387 records returned in a single call)

POST /ww/en/locate/api/partners/id-list-grouped
     ?configurationId=221&languageCode=en&countryCode=ww&ts=<epoch_ms>
     Body: {"ids": [id1, ..., id50]}
     -> Full partner details (50 IDs per batch, 68 total batches)
```

**Akamai bypass**: Playwright loads the full locator page first to acquire a
valid Akamai session. All subsequent API calls are made through the live browser
context (`page.evaluate("fetch(...)")`), which carries the session cookies
automatically.

**Cookie consent**: The OneTrust consent modal is bypassed by pre-setting
`OptanonConsent` cookies before the page loads — no UI interaction required.

## Architecture

Three `asyncio` agents run concurrently via `asyncio.gather()`:

```
BrowserAgent ──[raw_queue]──> ParserAgent ──[clean_queue]──> WriterAgent
```

| Agent | Responsibility |
|-------|---------------|
| `BrowserAgent` | Loads page, GETs all IDs, fans out concurrent batch POSTs |
| `ParserAgent` | Flattens nested JSON fields, writes JSONL backup |
| `WriterAgent` | Deduplicates rows, writes CSV, runs QA report |

## Known Issues

- Batches 65–66 occasionally return HTTP 500 (`RUNTIME_EXCEPTION: For input
  string: " Procurement"`). This is a data quality issue on Schneider Electric's
  side. The scraper retries up to 3 times with exponential backoff (2s → 4s → 8s)
  before logging the failure and continuing.

## License

MIT

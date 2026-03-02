# Future Improvements

Priority labels: **[High]** — significant value, low effort | **[Medium]** — good value, moderate effort | **[Low]** — nice-to-have, higher effort

---

## Robustness

### [High] GitHub Actions CI Pipeline

Add `.github/workflows/ci.yml` to run tests automatically on every push and
pull request. Currently all validation is manual.

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v
      - run: python -m se_scraper --help
```

### [High] Detect API Schema Changes Automatically

The SE API occasionally changes response shapes without notice. Add a lightweight
contract test that runs before the full scrape and aborts with a clear error if
the schema has changed:

```python
async def assert_api_contract(page) -> None:
    """Fail fast if the API response shape has changed."""
    r = await page.evaluate(f"fetch('{LOCATIONS_URL}', ...)")
    body = json.loads(r["body"])
    assert "partnerLocations" in body, "API schema changed: 'partnerLocations' key missing"
    sample = body["partnerLocations"][0]
    assert "id" in sample and "latitude" in sample, "partner location object schema changed"
```

### [Medium] Persistent Retry Queue for Failed Batches

Currently, permanently-failing batches (HTTP 500 due to SE backend data
corruption) are logged and skipped. Instead, write their IDs to a
`failed_batches.json` file so a subsequent run can retry only the failures
without re-fetching all 3,387 partners:

```python
# On permanent failure:
failed_ids_path = output_dir / "failed_ids.json"
with open(failed_ids_path, "a") as f:
    json.dump({"batch": batch_idx, "ids": batch_ids}, f)
    f.write("\n")

# Resume run:
# python -m se_scraper --retry-failed output/failed_ids.json
```

### [Medium] Incremental / Delta Runs

Compare the new CSV against the previous run's CSV and output only:
- New partners (IDs not in previous run)
- Changed partners (any field value differs)
- Removed partners (IDs in previous run but not in new run)

This reduces noise for downstream consumers who only need to act on changes.

```python
# python -m se_scraper --diff output/distributors_prev.csv
```

---

## Performance

### [High] Multiple Parallel Browser Contexts

Each Playwright browser supports multiple independent contexts (like separate
browser profiles). Running 2–3 parallel contexts multiplies throughput without
creating multiple Chromium processes:

```python
async def _fetch_all_details(self, browser, all_ids):
    contexts = await asyncio.gather(
        *[browser.new_context(...) for _ in range(3)]
    )
    # Distribute batches across contexts
    # Each context gets its own page and makes independent fetch calls
```

Estimated speedup: 2–3x, reducing total run time from ~60s to ~20–30s.

### [Medium] Streaming CSV Write

Currently all rows are accumulated in memory before writing the CSV. For very
large datasets (if SE adds more partners), switch to streaming row-by-row:

```python
import csv
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMN_ORDER)
    writer.writeheader()
    async for row in clean_queue:
        writer.writerow(row)
```

This keeps memory usage constant regardless of dataset size.

### [Low] Request Caching for Development

During probe/development runs, cache API responses to disk so you don't hit the
live API on every code change:

```python
# dev-only: cache responses in .cache/
import hashlib, pickle
cache_key = hashlib.md5(url.encode()).hexdigest()
cache_file = Path(".cache") / f"{cache_key}.pkl"
if cache_file.exists():
    return pickle.loads(cache_file.read_bytes())
result = await page.evaluate(...)
cache_file.write_bytes(pickle.dumps(result))
return result
```

---

## Data Quality

### [High] Validate and Normalise Country Names

The `country` field contains inconsistent values from SE's backend:
- "USA" and "United States" appear as separate countries
- "Korea" vs "South Korea"
- Special characters in French/German country names vary by encoding

Add a normalisation map in `extractor.py`:

```python
COUNTRY_ALIASES = {
    "USA": "United States",
    "Korea": "South Korea",
    "UK": "United Kingdom",
    # ...
}

def normalise_country(name: str) -> str:
    return COUNTRY_ALIASES.get(name.strip(), name.strip())
```

### [Medium] Geocoding Validation

Cross-validate `latitude`/`longitude` against `country` using a reverse-geocoding
service (e.g., OpenStreetMap Nominatim, which is free):

```python
# Flag partners whose coordinates don't match their declared country
# e.g., latitude=0, longitude=0 (default/null coordinates) should be NULL
```

### [Medium] Email and Phone Normalisation

Standardise phone numbers to E.164 format using the `phonenumbers` library:

```python
import phonenumbers
def normalise_phone(raw: str, country_code: str) -> str:
    try:
        parsed = phonenumbers.parse(raw, country_code)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return raw  # return original if parsing fails
```

### [Low] Programmatic QA Failure Thresholds

Currently `run_qa()` only prints a report. Add assertions that raise an exception
(or write an exit code) if quality falls below thresholds:

```python
assert fill_rates["id"] == 100.0, "ID column has gaps — data integrity failure"
assert fill_rates["companyName"] >= 99.0, f"companyName fill rate too low: {fill_rates['companyName']:.1f}%"
assert duplicate_ids == 0, f"Found {duplicate_ids} duplicate IDs"
```

---

## Usability

### [High] Multiple Output Formats

Add `--format` flag supporting `csv` (current), `json`, `excel`, and `sqlite`:

```bash
python -m se_scraper --format excel --output-dir ./output
# produces: distributors_YYYYMMDD.xlsx

python -m se_scraper --format sqlite --output-dir ./output
# produces: distributors.db with a `partners` table
```

SQLite is especially useful for downstream analysis without requiring pandas.

### [High] Support for Other SE Locator Pages

The scraper is hardcoded to configuration ID `221` (Industrial Automation
Distributors). SE runs dozens of partner locator pages with different config IDs:

```
config=221 — Industrial Automation Distributors
config=?   — Electrical Distributors
config=?   — IT Channel Partners
# etc.
```

Add `--config-id` as a CLI parameter to make the tool reusable across all SE
partner locator pages:

```bash
python -m se_scraper --config-id 221 --output-dir ./output/ia_distributors
python -m se_scraper --config-id 456 --output-dir ./output/electrical
```

### [Medium] Progress Bar

Replace the log-line counter with a rich progress bar using the `rich` library:

```python
from rich.progress import Progress, BarColumn, TaskProgressColumn

with Progress(BarColumn(), TaskProgressColumn()) as progress:
    task = progress.add_task("Fetching batches", total=total_batches)
    # ... update task after each batch ...
    progress.update(task, advance=1)
```

### [Medium] Docker Container

Package the scraper as a Docker image to eliminate the Playwright/Chromium
installation step entirely:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy
WORKDIR /app
COPY . .
RUN pip install -e .
ENTRYPOINT ["python", "-m", "se_scraper"]
```

```bash
docker build -t se-scraper .
docker run --rm -v $(pwd)/output:/app/output se-scraper --output-dir /app/output
```

### [Low] Webhook / Notification on Completion

Post a summary to Slack, Teams, or email when a run finishes:

```python
# In WriterAgent._write_csv():
if SLACK_WEBHOOK_URL:
    requests.post(SLACK_WEBHOOK_URL, json={
        "text": f"SE scraper complete: {len(df):,} partners → {csv_path.name}"
    })
```

---

## Maintenance

### [High] Automated Dependency Updates

Add `dependabot.yml` to receive automated PRs when Playwright, pandas, or
aiohttp release security patches:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
```

### [Medium] Changelog

Maintain a `CHANGELOG.md` using [Keep a Changelog](https://keepachangelog.com)
format. This makes it easy for users to see what changed between runs and whether
the output schema has changed.

### [Medium] API Version Monitoring

SE could change their API at any time. Set up a weekly cron job (GitHub Actions
scheduled workflow) that runs only the contract test and sends an alert if it
fails:

```yaml
# .github/workflows/api-monitor.yml
on:
  schedule:
    - cron: '0 6 * * 1'  # Every Monday at 06:00 UTC
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/ -m integration --tb=short
```

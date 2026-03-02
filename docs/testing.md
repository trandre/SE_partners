# Testing Recommendations

## Current Test Coverage

The project ships with 40 unit tests covering all pure-Python data extraction
logic in `se_scraper/extractor.py`. These tests run in ~0.6 seconds with zero
network access:

```bash
pytest tests/ -v
```

---

## What Is and Is Not Currently Tested

| Layer | Tested? | Notes |
|-------|---------|-------|
| `_s()` — safe string coercion | Yes | All edge cases: None, bool, int, whitespace |
| `_clean()` — control-char removal | Yes | Tab, newline, null byte, DEL, clean passthrough |
| `extract_record()` — field extraction | Yes | Scalars, nested objects, arrays, missing keys |
| `partner_list_from_body()` — response shaping | Yes | List, dict variants, empty, None |
| `COLUMN_ORDER` — schema integrity | Yes | No duplicates, correct ordering |
| `BrowserAgent` — Playwright integration | No | Requires live browser + network |
| `ParserAgent` — queue consumption | No | Requires running asyncio event loop |
| `WriterAgent` — CSV output | No | Requires filesystem + pandas |
| `run_qa()` — QA report | No | Requires populated DataFrame |
| Retry logic | No | Requires mock HTTP responses |

---

## Recommended Test Additions

### 1. Mock the Playwright `page.evaluate()` Call

Use `unittest.mock.AsyncMock` to inject canned API responses into
`BrowserAgent` without launching a real browser.

```python
# tests/test_browser_agent.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest, json
from se_scraper.agents import BrowserAgent, RunConfig
from pathlib import Path

FAKE_LOCATIONS = json.dumps({
    "partnerLocations": [
        {"id": 1, "latitude": 1.0, "longitude": 1.0},
        {"id": 2, "latitude": 2.0, "longitude": 2.0},
    ]
})

FAKE_DETAILS = json.dumps([
    {"id": 1, "companyName": "ACME", "country": "France"},
    {"id": 2, "companyName": "Beta", "country": "USA"},
])

@pytest.mark.asyncio
async def test_browser_agent_happy_path(tmp_path):
    queue = asyncio.Queue()
    cfg = RunConfig(
        csv_path=tmp_path / "out.csv",
        jsonl_path=tmp_path / "out.jsonl",
    )
    # Patch playwright so no real browser is launched
    with patch("se_scraper.agents.async_playwright") as mock_pw:
        mock_page = AsyncMock()
        mock_page.evaluate.side_effect = [
            {"status": 200, "body": FAKE_LOCATIONS},  # locations call
            {"status": 200, "body": FAKE_DETAILS},    # batch POST
        ]
        # ... wire up context manager chain ...
        await BrowserAgent(queue, cfg).run()

    results = []
    while not queue.empty():
        results.append(queue.get_nowait())
    assert len(results) == 2  # DONE sentinel + 1 batch
```

### 2. Test the Retry Logic in Isolation

Create a helper that simulates the `_post_batch_with_retry` sequence:

```python
@pytest.mark.asyncio
async def test_retry_succeeds_on_third_attempt():
    """Verify that a batch eventually succeeds after two 500 errors."""
    queue = asyncio.Queue()
    cfg = RunConfig(...)
    agent = BrowserAgent(queue, cfg)

    call_count = 0
    async def fake_evaluate(js_str):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return {"status": 500, "body": '{"code": "RUNTIME_EXCEPTION"}'}
        return {"status": 200, "body": json.dumps([{"id": 1, "companyName": "Test"}])}

    mock_page = AsyncMock()
    mock_page.evaluate.side_effect = fake_evaluate

    await agent._post_batch_with_retry(mock_page, "/fake-url", [1], 0, 1)
    assert call_count == 3
    assert queue.qsize() == 1
```

### 3. Test ParserAgent Queue Flow

```python
@pytest.mark.asyncio
async def test_parser_agent_flattens_records(tmp_path):
    raw_q   = asyncio.Queue()
    clean_q = asyncio.Queue()
    cfg = RunConfig(jsonl_path=tmp_path / "raw.jsonl", ...)

    raw_q.put_nowait({"body": [{"id": 1, "companyName": "Test Co"}]})
    raw_q.put_nowait(_DONE)  # sentinel

    await ParserAgent(raw_q, clean_q, cfg).run()

    row = clean_q.get_nowait()
    assert row["companyName"] == "Test Co"
    assert clean_q.get_nowait() is _DONE
```

### 4. Test WriterAgent CSV Output

```python
@pytest.mark.asyncio
async def test_writer_agent_writes_csv(tmp_path):
    clean_q = asyncio.Queue()
    csv_path = tmp_path / "output.csv"
    cfg = RunConfig(csv_path=csv_path, ...)

    clean_q.put_nowait({"id": "1", "companyName": "Alpha", "city": "Paris", "country": "France"})
    clean_q.put_nowait({"id": "1", "companyName": "Alpha", "city": "Paris", "country": "France"})  # duplicate
    clean_q.put_nowait({"id": "2", "companyName": "Beta", "city": "London", "country": "UK"})
    clean_q.put_nowait(_DONE)

    await WriterAgent(clean_q, cfg).run()

    df = pd.read_csv(csv_path)
    assert len(df) == 2  # duplicate removed
    assert "Alpha" in df["companyName"].values
```

### 5. Hypothesis-Based Property Testing

Use the `hypothesis` library for fuzz-testing `extract_record()` with arbitrary
inputs to find unexpected crashes:

```python
# pip install hypothesis
from hypothesis import given, strategies as st

@given(st.dictionaries(st.text(), st.one_of(
    st.none(), st.text(), st.integers(), st.booleans(),
    st.lists(st.dictionaries(st.text(), st.text())),
)))
def test_extract_record_never_raises(item):
    """extract_record() must not raise on any arbitrary dict input."""
    result = extract_record(item)
    assert isinstance(result, dict)
```

### 6. Contract Test the API Response Shape

Validate that the real API still returns the expected schema after any SE-side
changes:

```python
# tests/test_api_contract.py  (integration — skip in CI unless --run-integration)
import pytest, json
# Run only when explicitly requested:
# pytest tests/ -m integration
@pytest.mark.integration
async def test_locations_response_shape(live_page):
    """Confirm /locations still returns partnerLocations with id/lat/lng."""
    from se_scraper.config import LOCATIONS_URL
    result = await live_page.evaluate(f"fetch('{LOCATIONS_URL}', ...)")
    body = json.loads(result["body"])
    assert "partnerLocations" in body
    pl = body["partnerLocations"]
    assert len(pl) > 3000
    assert all("id" in p and "latitude" in p for p in pl[:10])
```

---

## CI/CD Recommendations

### GitHub Actions Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run unit tests
        run: pytest tests/ -v --tb=short

      - name: Verify CLI help
        run: python -m se_scraper --help
```

Key decisions:
- **Do not run the full scraper in CI.** It takes ~60s, hits a live API, and
  produces output files that would need to be managed as artifacts.
- **Only unit tests in CI.** Integration/browser tests are for local validation
  before a release.
- Mark integration tests with `@pytest.mark.integration` and use
  `pytest -m "not integration"` in CI.

---

## Test Data Strategy

Do not use real SE API responses as test fixtures. Instead:

1. **Inline minimal dicts** (as `MINIMAL_ITEM` in `test_extractor.py`): fast,
   readable, zero dependencies.
2. **Snapshot one real raw response** in `tests/fixtures/sample_batch.json`
   (commit once, update manually on schema change): useful for
   `partner_list_from_body` edge cases.
3. **Never commit full-run JSONL** output to the repo — it's 4 MB of live data
   that changes every run.

---

## Coverage Target

Run with coverage to identify gaps:

```bash
pip install pytest-cov
pytest tests/ --cov=se_scraper --cov-report=term-missing
```

Current baseline: ~85% coverage of `extractor.py`. Target: **100%** for
`extractor.py`, **>70%** overall (browser/network code is intentionally excluded
from automated coverage).

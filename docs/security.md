# Security Considerations

---

## 1. Scraped Data — Storage and Handling

**Risk:** The output CSV contains personal data (names, emails, phone numbers,
addresses) of named individuals at partner companies. This likely falls under
GDPR (EU partners), CCPA (US partners), and similar regulations.

**Recommendations:**
- Do not commit `output/` to the repository. The `.gitignore` already excludes
  all CSV, JSONL, and log files. Verify with `git status` before every push.
- Store output files in a location with access controls (not a public S3 bucket
  or shared network drive).
- Apply data minimisation: if downstream consumers only need company-level data,
  drop `firstName`, `lastName`, `contact_email`, and `contact_phone` columns
  before sharing.
- Define a retention policy: delete output files after use rather than
  accumulating runs indefinitely in the output directory.

---

## 2. Credential and Secret Management

**Current state:** No credentials are required or stored. The scraper accesses
a publicly reachable API that uses session-based Akamai authentication (no API
key, no login).

**Risks to watch for:**
- If Schneider Electric adds authentication (API key, OAuth), do **not** store
  credentials in `config.py`. Use environment variables or a secrets manager
  instead:

  ```python
  # config.py — correct pattern
  import os
  API_KEY = os.environ.get("SE_API_KEY", "")  # empty = unauthenticated
  ```

- The `CONSENT_COOKIES` in `config.py` are pre-set consent values, not secrets.
  They do not grant elevated access and are safe to commit.

- Never add `.env` files to the repo. If you add one locally, add `.env` to
  `.gitignore` immediately.

---

## 3. Rate Limiting and Responsible Use

**Risk:** Running the scraper with very high concurrency (e.g., `--concurrency 50`)
could cause significant load on SE's servers, which could be interpreted as
a denial-of-service attack.

**Current safeguards:**
- Default concurrency: 6 parallel POST requests per group
- `BATCH_DELAY = 0.4s` pause between groups
- Total run time ~60s for 3,387 records — a modest, human-scale request rate

**Recommendations:**
- Do not lower `BATCH_DELAY` below 0.2s or raise `CONCURRENT_POSTS` above 10
  without explicit authorisation from the data owner.
- Add jitter to `BATCH_DELAY` to avoid synchronized burst patterns:
  ```python
  import random
  await asyncio.sleep(BATCH_DELAY + random.uniform(0, 0.2))
  ```
- Monitor HTTP 429 (Too Many Requests) responses and add automatic backoff:
  ```python
  if status == 429:
      retry_after = int(result.get("headers", {}).get("Retry-After", 60))
      await asyncio.sleep(retry_after)
  ```
- Schedule production runs during off-peak hours (e.g., 02:00–04:00 UTC).

---

## 4. Terms of Service and Legal Compliance

**Risk:** Automated scraping may violate Schneider Electric's Terms of Use even
if the API is technically accessible.

**Recommendations:**
- Review SE's Terms of Use at [se.com/terms](https://www.se.com) before using
  this scraper in a production or commercial context.
- Check `robots.txt`: `https://www.se.com/robots.txt` — verify the `/ww/en/locate/`
  path is not disallowed.
- If using data commercially or sharing it externally, obtain explicit written
  authorisation from Schneider Electric.
- This scraper was built for internal/research use. Redistribute the output data
  only if you have a legal basis to do so.

---

## 5. Dependency Supply Chain Security

**Risk:** The three runtime dependencies (Playwright, pandas, aiohttp) and their
transitive dependencies are a potential attack surface.

**Recommendations:**

**Pin exact versions in production:**
```
# requirements-lock.txt (for production deployments)
playwright==1.51.0
pandas==2.2.3
aiohttp==3.11.13
```
Use `pip-compile` (from `pip-tools`) to generate a fully-pinned lockfile from
`pyproject.toml`.

**Audit dependencies for known CVEs:**
```bash
pip install pip-audit
pip-audit
```
Run this before every production deployment and as a CI check.

**Verify Playwright's Chromium hash:**
Playwright downloads Chromium automatically. The binary hash is checked against
the Playwright release manifest. Do not override or skip this verification.

---

## 6. Command Injection via `page.evaluate()`

**Risk:** The `page.evaluate(f"fetch('{url}', ...)")` pattern embeds a Python
string directly into JavaScript. If `url` ever contained user input or came from
an external source, a malicious value could break out of the string literal and
inject arbitrary JavaScript.

**Current state:** All URLs are built from hardcoded constants in `config.py`.
The only dynamic part is `ts={int(time.time() * 1000)}` (an integer — safe).
No user input ever reaches `page.evaluate()`.

**Recommendation:**
If you ever add a `--target-url` CLI flag or make the URL configurable at
runtime, sanitise it before embedding:

```python
import urllib.parse

def safe_js_string(value: str) -> str:
    """Escape a string for safe embedding in a JS string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

url = safe_js_string(user_provided_url)
await page.evaluate(f"fetch('{url}', ...)")
```

Or better, use Playwright's `page.request.fetch()` API which accepts Python
arguments and never constructs a JS string:

```python
response = await page.request.fetch(url, method="POST", data={"ids": batch_ids})
```

---

## 7. Output File Permissions

**Risk:** CSV and JSONL output files are created with default umask permissions
(`-rw-rw-r--` on most Linux systems), making them world-readable on shared
servers.

**Recommendation:**
Set restrictive permissions on the output directory at creation time:

```python
# In config.py or __main__.py
output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
```

Or restrict after writing:
```python
csv_path.chmod(0o600)
jsonl_path.chmod(0o600)
```

---

## 8. Playwright Browser Security

**Risk:** Playwright's headless Chromium downloads and executes arbitrary web
content (the SE locator page and its JavaScript bundle) in a real browser process.

**Mitigations already in place:**
- The browser is launched with `headless=True`
- No `--no-sandbox` flag is used (sandboxing is active)
- Only one specific, known domain is loaded (`se.com`)

**Recommendations:**
- Do not add `--disable-web-security` or other security-relaxing Chromium flags.
- Consider running the scraper in a Docker container with limited capabilities
  (`--cap-drop=ALL --cap-add=SYS_ADMIN` for Chrome's sandbox requirements) to
  isolate the browser process from the host filesystem.
- Review the `args` parameter if you ever extend `pw.chromium.launch()`.

---

## Security Checklist Before Each Production Run

- [ ] `git status` — confirm no secrets or output files are staged
- [ ] `pip-audit` — no known CVEs in dependencies
- [ ] Output directory permissions are `700`
- [ ] Run scheduled at off-peak hours (respect the API)
- [ ] Output files will be deleted or encrypted at rest after use
- [ ] Downstream consumers of the CSV have a legal basis for the personal data

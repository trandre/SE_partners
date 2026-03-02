"""
config.py — All constants for the SE Partner Locator scraper.

Edit this file to change URLs, batch sizes, timeouts, or cookie values.
Do NOT scatter magic numbers across other modules.
"""

from datetime import datetime
from pathlib import Path

# ── Output paths ──────────────────────────────────────────────────────────────
# The default output directory.  __main__.py may override via --output-dir.
DEFAULT_OUTPUT_DIR: Path = Path("output")


def make_output_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    """
    Return (csv_path, jsonl_path, log_path) stamped with the current time.

    Called once at startup so all three files share the same timestamp.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        output_dir / f"distributors_{ts}.csv",
        output_dir / f"raw_responses_{ts}.jsonl",
        output_dir / f"scraper_{ts}.log",
    )


# ── API endpoints ─────────────────────────────────────────────────────────────
SE_BASE: str = "https://www.se.com"

LOCATOR_PAGE: str = (
    "https://www.se.com/ww/en/locate/"
    "221-find-an-industrial-automation-distributor-near-you"
)

# Note: the locations endpoint uses 'config=221', NOT 'configurationId=221'
LOCATIONS_URL: str = (
    "/ww/en/locate/api/partners/locations"
    "?config=221&languageCode=en&countryCode=ww"
)

DETAILS_PATH: str = "/ww/en/locate/api/partners/id-list-grouped"
DETAILS_PARAMS: str = "configurationId=221&languageCode=en&countryCode=ww"

# ── Tuning knobs ──────────────────────────────────────────────────────────────
POST_BATCH_SIZE: int = 50     # IDs per POST to id-list-grouped
CONCURRENT_POSTS: int = 6     # parallel POST requests at once
BATCH_DELAY: float = 0.4      # seconds between batch groups (rate-limit courtesy)
PAGE_LOAD_WAIT: int = 6       # seconds after page load before API calls

# Retry settings for failed batches (HTTP 500 / parse errors)
MAX_BATCH_RETRIES: int = 3    # number of retry attempts per failed batch
RETRY_BACKOFF: float = 2.0    # seconds before first retry (doubles each attempt)

# ── Browser fingerprint ───────────────────────────────────────────────────────
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)
VIEWPORT: dict = {"width": 1920, "height": 1080}

# ── Cookie consent bypass ─────────────────────────────────────────────────────
# Pre-set these cookies so the OneTrust consent modal never appears.
CONSENT_COOKIES: list[dict] = [
    {
        "name": "OptanonAlertBoxClosed",
        "value": "2024-01-01T00:00:00.000Z",
        "domain": ".se.com",
        "path": "/",
    },
    {
        "name": "OptanonConsent",
        "value": (
            "isGpcEnabled=0&datestamp=Mon+Jan+01+2024&version=202209.1.0"
            "&consentId=consent-bypass&interactionCount=1"
            "&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1"
        ),
        "domain": ".se.com",
        "path": "/",
    },
]

# ── Logging format ────────────────────────────────────────────────────────────
LOG_FORMAT: str = "%(asctime)s  [%(name)s]  %(levelname)-8s  %(message)s"

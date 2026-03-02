#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# run.sh  —  venv bootstrap + dependency install + scraper execution
# Usage:  bash run.sh [--output-dir DIR] [--batch-size N] [--concurrency N]
#         All arguments are forwarded to `python -m se_scraper`.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Schneider Electric Partner Scraper — venv bootstrap        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Create venv if missing ─────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/4] Creating virtual environment at $VENV_DIR …"
    python3 -m venv "$VENV_DIR"
else
    echo "[1/4] Virtual environment already exists — skipping creation."
fi

# ── 2. Activate ───────────────────────────────────────────────────────────────
echo "[2/4] Activating venv …"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── 3. Install / upgrade Python dependencies ─────────────────────────────────
echo "[3/4] Installing Python dependencies …"
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# ── 4. Install Playwright's bundled Chromium (no system Chrome needed) ───────
echo "[4/4] Ensuring Playwright Chromium is installed …"
# 'playwright install chromium' downloads the browser binary to ~/.cache/ms-playwright
# It does NOT require sudo — everything goes into the user's home directory.
python -m playwright install chromium

echo ""
echo "──────────────────────────────────────────────────────────────"
echo "  All dependencies ready.  Starting scraper …"
echo "──────────────────────────────────────────────────────────────"
echo ""

# ── Run the package from the project directory ───────────────────────────────
# $@ forwards any CLI arguments to se_scraper:
#   bash run.sh --output-dir /data  =>  python -m se_scraper --output-dir /data
cd "$SCRIPT_DIR"
python -m se_scraper "$@"

echo ""
echo "Done.  Check $SCRIPT_DIR/output/ for results."

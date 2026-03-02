"""
qa.py — QA Bot: validates the output CSV and prints a quality report.

Completely stateless — call run_qa() after writing the CSV.
"""

import logging
from pathlib import Path

import pandas as pd


def run_qa(df: pd.DataFrame, csv_path: Path, jsonl_path: Path) -> None:
    """
    Validate the output DataFrame and print a detailed quality report.

    Checks:
        - Fill rates for every column
        - Coordinate validity (latitude/longitude must be numeric)
        - Duplicate IDs
        - Top 20 country distribution
        - Business type breakdown
        - First 3 sample rows

    Args:
        df:         The final deduplicated DataFrame.
        csv_path:   Path to the written CSV file (for display only).
        jsonl_path: Path to the raw JSONL backup (for display only).
    """
    log = logging.getLogger("QABot")
    log.info("Running quality validation ...")

    sep = "=" * 64
    print(f"\n{sep}")
    print("  QA REPORT  —  Schneider Electric Partner Locator")
    print(sep)
    print(f"  Total rows      : {len(df):,}")
    print(f"  Total columns   : {len(df.columns)}")
    print(f"  CSV file        : {csv_path.resolve()}")
    print(f"  Raw backup      : {jsonl_path.resolve()}")
    print(sep)

    # ── Column fill rates ─────────────────────────────────────────────────────
    print("\n  Column fill rates (% non-empty):")
    fill_rates: dict[str, float] = {}
    for col in df.columns:
        n = (df[col].astype(str).str.strip() != "").sum()
        fill_rates[col] = 100.0 * n / len(df) if len(df) else 0.0
    for col, pct in sorted(fill_rates.items(), key=lambda x: -x[1]):
        bar  = "#" * int(pct / 5)
        flag = "  <- LOW" if pct < 10 else ""
        print(f"    {col:<40s}  {pct:5.1f}%  {bar}{flag}")

    # ── Geo sanity ────────────────────────────────────────────────────────────
    if "latitude" in df.columns and "longitude" in df.columns:
        bad_lat = pd.to_numeric(df["latitude"], errors="coerce").isna().sum()
        bad_lon = pd.to_numeric(df["longitude"], errors="coerce").isna().sum()
        print(f"\n  Bad latitude values  : {bad_lat}")
        print(f"  Bad longitude values : {bad_lon}")

    # ── Duplicate IDs ─────────────────────────────────────────────────────────
    if "id" in df.columns:
        dup = df["id"].duplicated().sum()
        print(f"  Duplicate IDs        : {dup}")

    # ── Country distribution ──────────────────────────────────────────────────
    if "country" in df.columns:
        top = df["country"].value_counts().head(20)
        print("\n  Top 20 countries:")
        for country, cnt in top.items():
            print(f"    {country:<40s}  {cnt:>5,}")

    # ── Business type distribution ────────────────────────────────────────────
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

    # ── Sample rows ───────────────────────────────────────────────────────────
    show_cols = [
        c for c in (
            "companyName", "city", "country",
            "contact_email", "contact_phone",
            "businessType_names",
        )
        if c in df.columns
    ]
    print(f"\n  First 3 rows ({', '.join(show_cols)}):")
    print(df[show_cols].head(3).to_string(index=False))
    print(f"\n{sep}\n")

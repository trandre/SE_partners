"""
__main__.py — Entry point for ``python -m se_scraper``.

Examples::

    python -m se_scraper
    python -m se_scraper --output-dir /data/se_output
    python -m se_scraper --batch-size 25 --concurrency 3
    python -m se_scraper --help
"""

import argparse
import asyncio
import logging
import time
from pathlib import Path

from .agents import BrowserAgent, ParserAgent, RunConfig, WriterAgent
from .config import (
    CONCURRENT_POSTS,
    DEFAULT_OUTPUT_DIR,
    LOG_FORMAT,
    POST_BATCH_SIZE,
    make_output_paths,
)


def _setup_logging(log_path: Path) -> None:
    """Configure root logger to write to both a file and stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="se_scraper",
        description=(
            "Schneider Electric Partner Locator — async scraper.\n"
            "Fetches all ~3,387 partner/distributor records and writes CSV + JSONL."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help="Directory for output files",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=POST_BATCH_SIZE,
        metavar="N",
        help="IDs per POST batch",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=CONCURRENT_POSTS,
        metavar="N",
        help="Concurrent POST requests per group",
    )
    return parser.parse_args()


async def _run(cfg: RunConfig) -> None:
    raw_queue   = asyncio.Queue()
    clean_queue = asyncio.Queue()

    await asyncio.gather(
        BrowserAgent(raw_queue, cfg).run(),
        ParserAgent(raw_queue, clean_queue, cfg).run(),
        WriterAgent(clean_queue, cfg).run(),
    )


def main() -> None:
    args = _parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path, jsonl_path, log_path = make_output_paths(output_dir)

    _setup_logging(log_path)
    log = logging.getLogger("Main")

    cfg = RunConfig(
        csv_path    = csv_path,
        jsonl_path  = jsonl_path,
        batch_size  = args.batch_size,
        concurrency = args.concurrency,
    )

    log.info("=" * 64)
    log.info("SE Partner Locator Scraper  (3-Agent Async + QA Bot)")
    log.info(f"Output dir : {output_dir.resolve()}")
    log.info(f"CSV        : {csv_path.name}")
    log.info(f"Batch size : {cfg.batch_size}  Concurrency: {cfg.concurrency}")
    log.info("=" * 64)

    t0 = time.perf_counter()
    asyncio.run(_run(cfg))
    elapsed = time.perf_counter() - t0
    log.info(f"Total elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()

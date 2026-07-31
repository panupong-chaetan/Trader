from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from data.client import create_ccxt_fetcher
from data.config import DownloadConfig
from data.exceptions import DataIntegrityError
from data.pipeline import run

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.data.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download and validate OHLCV data")
    download.add_argument("--symbol", required=True)
    download.add_argument("--timeframe", required=True)
    download.add_argument("--start", required=True, type=_parse_datetime)
    download.add_argument("--end", type=_parse_datetime, default=None)
    download.add_argument("--exchange", default="binance")
    download.add_argument("--small-gap-max", type=int, default=5, dest="small_gap_max")
    download.add_argument("--medium-gap-max", type=int, default=20, dest="medium_gap_max")
    download.add_argument("--retry-count", type=int, default=1, dest="retry_count")

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = build_parser()
    args = parser.parse_args(argv)

    config = DownloadConfig(
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        small_gap_max=args.small_gap_max,
        medium_gap_max=args.medium_gap_max,
        retry_count=args.retry_count,
    )
    fetcher = create_ccxt_fetcher(config.exchange)

    try:
        result = run(config, fetcher, DEFAULT_DATA_DIR)
    except DataIntegrityError as error:
        logging.getLogger(__name__).error("Data integrity check failed: %s", error)
        return 1

    logging.getLogger(__name__).info(
        "Download finished with status=%s row_count=%d", result.status, result.row_count
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

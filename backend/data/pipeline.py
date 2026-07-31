from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from data.client import OHLCVFetcher, fetch_ohlcv_range
from data.config import DownloadConfig
from data.exceptions import DataIntegrityError
from data.storage import (
    atomic_write,
    build_metadata,
    dataset_paths,
    read_metadata_if_exists,
    read_parquet_if_exists,
    reconcile_metadata,
)
from data.validator import Gap, deduplicate, find_gaps, sort_by_timestamp, timeframe_to_timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    status: str
    row_count: int
    gaps: list[Gap]


def run(config: DownloadConfig, fetcher: OHLCVFetcher, base_dir: Path) -> PipelineResult:
    paths = dataset_paths(base_dir, config.exchange, config.symbol_slug, config.timeframe)
    existing_df = read_parquet_if_exists(paths.parquet_path)
    interval = timeframe_to_timedelta(config.timeframe)

    if existing_df is not None:
        existing_metadata = read_metadata_if_exists(paths.metadata_path)
        reconcile_metadata(existing_df, existing_metadata, config)
        fetch_start = existing_df["timestamp"].max() + interval
    else:
        fetch_start = config.start

    fetch_end = config.end or datetime.now(timezone.utc)

    new_df = fetch_ohlcv_range(fetcher, config.symbol, config.timeframe, fetch_start, fetch_end)
    merged_df = pl.concat([existing_df, new_df]) if existing_df is not None else new_df
    merged_df = sort_by_timestamp(merged_df)
    merged_df = deduplicate(merged_df)

    gaps = find_gaps(merged_df, config.timeframe, config.small_gap_max, config.medium_gap_max)
    large_gaps = [g for g in gaps if g.severity == "large"]
    if large_gaps:
        first = large_gaps[0]
        raise DataIntegrityError(
            f"Large gap of {first.missing_candles} missing candles between "
            f"{first.start} and {first.end}",
            start=str(first.start),
            end=str(first.end),
        )

    unresolved_gaps = [g for g in gaps if g.severity in ("small", "medium")]

    for _attempt in range(config.retry_count):
        if not unresolved_gaps:
            break
        for gap in list(unresolved_gaps):
            refetched = fetch_ohlcv_range(fetcher, config.symbol, config.timeframe, gap.start, gap.end)
            if refetched.height == 0:
                continue
            merged_df = pl.concat([merged_df, refetched])
            merged_df = sort_by_timestamp(merged_df)
            merged_df = deduplicate(merged_df)
        unresolved_gaps = [
            g
            for g in find_gaps(merged_df, config.timeframe, config.small_gap_max, config.medium_gap_max)
            if g.severity in ("small", "medium")
        ]

    for gap in unresolved_gaps:
        logger.warning(
            "Unresolved %s gap of %d candles between %s and %s after %d retries",
            gap.severity,
            gap.missing_candles,
            gap.start,
            gap.end,
            config.retry_count,
        )

    status = "incomplete" if unresolved_gaps else "complete"
    metadata = build_metadata(merged_df, config, unresolved_gaps, status)
    atomic_write(merged_df, metadata, paths)

    return PipelineResult(status=status, row_count=merged_df.height, gaps=unresolved_gaps)

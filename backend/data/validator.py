from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl

from data.exceptions import DataIntegrityError

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")

_TIMEFRAME_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def sort_by_timestamp(df: pl.DataFrame) -> pl.DataFrame:
    return df.sort("timestamp")


def deduplicate(df: pl.DataFrame) -> pl.DataFrame:
    duplicate_timestamps = (
        df.group_by("timestamp")
        .agg(pl.len().alias("count"))
        .filter(pl.col("count") > 1)
        .get_column("timestamp")
    )

    if duplicate_timestamps.is_empty():
        return df

    for timestamp in duplicate_timestamps:
        rows = df.filter(pl.col("timestamp") == timestamp)
        distinct_rows = rows.select(list(OHLCV_COLUMNS)).unique()
        if distinct_rows.height > 1:
            raise DataIntegrityError(
                f"Conflicting OHLCV values for duplicate timestamp {timestamp}",
                start=str(timestamp),
                end=str(timestamp),
            )
        logger.warning(
            "Dropping %d identical duplicate rows at timestamp %s",
            rows.height - 1,
            timestamp,
        )

    return df.unique(subset=["timestamp"], keep="first").sort("timestamp")


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    unit = timeframe[-1]
    if unit not in _TIMEFRAME_UNITS:
        raise ValueError(f"Unsupported timeframe unit: {timeframe!r}")
    amount = int(timeframe[:-1])
    return timedelta(**{_TIMEFRAME_UNITS[unit]: amount})


@dataclass(frozen=True)
class Gap:
    start: datetime
    end: datetime
    missing_candles: int
    severity: str


def classify_gap(missing_candles: int, small_gap_max: int, medium_gap_max: int) -> str:
    if missing_candles <= small_gap_max:
        return "small"
    if missing_candles <= medium_gap_max:
        return "medium"
    return "large"


def find_gaps(
    df: pl.DataFrame,
    timeframe: str,
    small_gap_max: int,
    medium_gap_max: int,
) -> list[Gap]:
    interval = timeframe_to_timedelta(timeframe)
    timestamps = df["timestamp"].to_list()
    gaps: list[Gap] = []

    for previous, current in zip(timestamps, timestamps[1:]):
        expected_next = previous + interval
        if current == expected_next:
            continue
        missing_candles = int((current - previous) / interval) - 1
        gaps.append(
            Gap(
                start=expected_next,
                end=current - interval,
                missing_candles=missing_candles,
                severity=classify_gap(missing_candles, small_gap_max, medium_gap_max),
            )
        )

    return gaps

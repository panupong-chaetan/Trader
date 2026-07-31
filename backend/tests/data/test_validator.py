from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from data.exceptions import DataIntegrityError
from data.validator import classify_gap, deduplicate, find_gaps, sort_by_timestamp, timeframe_to_timedelta


def _row(ts: datetime, close: float = 100.0) -> dict:
    return {
        "timestamp": ts,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def test_sort_by_timestamp_orders_ascending() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t1), _row(t0)])

    sorted_df = sort_by_timestamp(df)

    assert sorted_df["timestamp"].to_list() == [t0, t1]


def test_deduplicate_drops_identical_duplicate_rows() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t0), _row(t0)])

    result = deduplicate(df)

    assert result.height == 1


def test_deduplicate_raises_on_conflicting_duplicate() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t0, close=100.0), _row(t0, close=101.0)])

    with pytest.raises(DataIntegrityError):
        deduplicate(df)


def test_deduplicate_leaves_unique_rows_untouched() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t0), _row(t1)])

    result = deduplicate(df)

    assert result.height == 2


def _candles(start: datetime, count: int, interval: timedelta, skip: set[int] | None = None) -> pl.DataFrame:
    skip = skip or set()
    rows = [_row(start + i * interval) for i in range(count) if i not in skip]
    return pl.DataFrame(rows)


def test_timeframe_to_timedelta_parses_minutes_hours_days() -> None:
    assert timeframe_to_timedelta("15m") == timedelta(minutes=15)
    assert timeframe_to_timedelta("1h") == timedelta(hours=1)
    assert timeframe_to_timedelta("1d") == timedelta(days=1)


def test_classify_gap_boundaries() -> None:
    assert classify_gap(5, small_gap_max=5, medium_gap_max=20) == "small"
    assert classify_gap(6, small_gap_max=5, medium_gap_max=20) == "medium"
    assert classify_gap(20, small_gap_max=5, medium_gap_max=20) == "medium"
    assert classify_gap(21, small_gap_max=5, medium_gap_max=20) == "large"


def test_find_gaps_detects_no_gap_in_contiguous_data() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _candles(start, 10, timedelta(minutes=15))

    assert find_gaps(df, "15m", small_gap_max=5, medium_gap_max=20) == []


def test_find_gaps_detects_small_gap() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _candles(start, 10, timedelta(minutes=15), skip={3, 4})

    gaps = find_gaps(df, "15m", small_gap_max=5, medium_gap_max=20)

    assert len(gaps) == 1
    assert gaps[0].missing_candles == 2
    assert gaps[0].severity == "small"


def test_find_gaps_detects_large_gap() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _candles(start, 30, timedelta(minutes=15), skip=set(range(3, 25)))

    gaps = find_gaps(df, "15m", small_gap_max=5, medium_gap_max=20)

    assert len(gaps) == 1
    assert gaps[0].severity == "large"

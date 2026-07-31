from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import ccxt
import polars as pl

from data.validator import timeframe_to_timedelta

DEFAULT_PAGE_LIMIT = 1000


class OHLCVFetcher(Protocol):
    def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int, limit: int
    ) -> list[list[float]]: ...


def create_ccxt_fetcher(exchange: str) -> OHLCVFetcher:
    exchange_class = getattr(ccxt, exchange)
    return exchange_class({"enableRateLimit": True})


def fetch_ohlcv_range(
    fetcher: OHLCVFetcher,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> pl.DataFrame:
    interval_ms = int(timeframe_to_timedelta(timeframe).total_seconds() * 1000)
    since_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    rows: list[list[float]] = []
    while since_ms <= end_ms:
        batch = fetcher.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        if not batch:
            break
        rows.extend(candle for candle in batch if candle[0] <= end_ms)
        last_ts = batch[-1][0]
        if last_ts > end_ms or len(batch) < limit:
            break
        since_ms = last_ts + interval_ms

    return _rows_to_dataframe(rows)


def _rows_to_dataframe(rows: list[list[float]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        )
    return pl.DataFrame(
        {
            "timestamp": [datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc) for row in rows],
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [row[5] for row in rows],
        }
    )

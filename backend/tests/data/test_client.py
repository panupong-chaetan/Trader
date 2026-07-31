from datetime import datetime, timedelta, timezone

from data.client import fetch_ohlcv_range


class ListFetcher:
    def __init__(self, candles: list[list[float]]) -> None:
        self._candles = candles

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return [c for c in self._candles if c[0] >= since][:limit]


def _candle(ts: datetime, price: float) -> list[float]:
    return [int(ts.timestamp() * 1000), price, price, price, price, 1.0]


def test_fetch_ohlcv_range_paginates_across_multiple_batches() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    interval = timedelta(minutes=15)
    candles = [_candle(start + i * interval, 100.0 + i) for i in range(5)]
    fetcher = ListFetcher(candles)

    df = fetch_ohlcv_range(fetcher, "BTC/USDT", "15m", start, start + 4 * interval, limit=2)

    assert df.height == 5
    assert df["timestamp"].to_list() == [start + i * interval for i in range(5)]
    assert df.columns == ["timestamp", "open", "high", "low", "close", "volume"]


def test_fetch_ohlcv_range_returns_empty_dataframe_when_no_data() -> None:
    fetcher = ListFetcher([])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    df = fetch_ohlcv_range(fetcher, "BTC/USDT", "15m", start, start)

    assert df.height == 0
    assert df.columns == ["timestamp", "open", "high", "low", "close", "volume"]

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from data.config import DownloadConfig
from data.exceptions import DataIntegrityError
from data.pipeline import run
from data.storage import atomic_write, build_metadata, dataset_paths

INTERVAL = timedelta(minutes=15)
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


class ListFetcher:
    def __init__(self, candles: list[list[float]]) -> None:
        self._candles = candles

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return [c for c in self._candles if c[0] >= since][:limit]


def _candle(ts: datetime, price: float = 100.0) -> list[float]:
    return [int(ts.timestamp() * 1000), price, price, price, price, 1.0]


def _contiguous_candles(count: int, skip: set[int] | None = None) -> list[list[float]]:
    skip = skip or set()
    return [_candle(START + i * INTERVAL, 100.0 + i) for i in range(count) if i not in skip]


def _config(**overrides) -> DownloadConfig:
    kwargs = {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "start": START,
        "end": START + 19 * INTERVAL,
        "retry_count": 1,
    }
    kwargs.update(overrides)
    return DownloadConfig(**kwargs)


def _seed_dataframe(count: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * INTERVAL for i in range(count)],
            "open": [100.0 + i for i in range(count)],
            "high": [100.0 + i for i in range(count)],
            "low": [100.0 + i for i in range(count)],
            "close": [100.0 + i for i in range(count)],
            "volume": [1.0 for _ in range(count)],
        }
    )


def test_run_full_download_with_no_gaps_marks_complete(tmp_path: Path) -> None:
    config = _config()
    fetcher = ListFetcher(_contiguous_candles(20))

    result = run(config, fetcher, tmp_path)

    assert result.status == "complete"
    assert result.row_count == 20
    assert result.gaps == []
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    assert paths.parquet_path.exists()
    assert paths.metadata_path.exists()


def test_run_incremental_only_fetches_delta(tmp_path: Path) -> None:
    config = _config()
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    seed_df = _seed_dataframe(10)
    seed_metadata = build_metadata(seed_df, config, gaps=[], status="complete")
    atomic_write(seed_df, seed_metadata, paths)

    fetcher = ListFetcher(_contiguous_candles(20))
    result = run(config, fetcher, tmp_path)

    assert result.status == "complete"
    assert result.row_count == 20


def test_run_unresolved_small_gap_marks_incomplete(tmp_path: Path) -> None:
    config = _config(end=START + 19 * INTERVAL, retry_count=1)
    fetcher = ListFetcher(_contiguous_candles(20, skip={5}))

    result = run(config, fetcher, tmp_path)

    assert result.status == "incomplete"
    assert len(result.gaps) == 1
    assert result.gaps[0].severity == "small"
    assert result.gaps[0].missing_candles == 1


def test_run_unresolved_medium_gap_marks_incomplete(tmp_path: Path) -> None:
    config = _config(end=START + 29 * INTERVAL, retry_count=1)
    fetcher = ListFetcher(_contiguous_candles(30, skip=set(range(5, 13))))

    result = run(config, fetcher, tmp_path)

    assert result.status == "incomplete"
    assert len(result.gaps) == 1
    assert result.gaps[0].severity == "medium"
    assert result.gaps[0].missing_candles == 8


def test_run_large_gap_raises_and_preserves_previous_dataset(tmp_path: Path) -> None:
    config = _config(end=START + 29 * INTERVAL)
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)

    seed_df = _seed_dataframe(1)
    seed_metadata = build_metadata(seed_df, config, gaps=[], status="complete")
    atomic_write(seed_df, seed_metadata, paths)
    original_parquet_bytes = paths.parquet_path.read_bytes()
    original_metadata_text = paths.metadata_path.read_text()

    fetcher = ListFetcher(_contiguous_candles(30, skip=set(range(2, 25))))

    with pytest.raises(DataIntegrityError):
        run(config, fetcher, tmp_path)

    assert paths.parquet_path.read_bytes() == original_parquet_bytes
    assert paths.metadata_path.read_text() == original_metadata_text

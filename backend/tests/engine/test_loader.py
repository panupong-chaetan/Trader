from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from data.config import DownloadConfig
from data.storage import atomic_write, build_metadata, dataset_paths
from engine.loader import load_dataset


def test_load_dataset_returns_dataframe_and_matching_quality(tmp_path: Path) -> None:
    config = DownloadConfig(
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="15m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame(
        [{"timestamp": t0, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    )
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status="complete")
    atomic_write(df, metadata, paths)

    loaded_df, quality = load_dataset(tmp_path, config.exchange, config.symbol_slug, config.timeframe)

    assert loaded_df.height == 1
    assert quality.status == "complete"
    assert quality.gaps == []


def test_load_dataset_raises_when_parquet_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path, "binance", "BTCUSDT", "15m")

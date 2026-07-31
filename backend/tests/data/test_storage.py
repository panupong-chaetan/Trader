from datetime import datetime, timezone

import polars as pl
import pytest

from data.config import DownloadConfig
from data.storage import (
    atomic_write,
    build_metadata,
    dataset_paths,
    read_metadata_if_exists,
    read_parquet_if_exists,
    reconcile_metadata,
)


def _config(**overrides) -> DownloadConfig:
    kwargs = {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "start": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    kwargs.update(overrides)
    return DownloadConfig(**kwargs)


def _df(*timestamps: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"timestamp": ts, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
            for ts in timestamps
        ]
    )


def test_dataset_paths_uses_symbol_slug(tmp_path) -> None:
    paths = dataset_paths(tmp_path, "binance", "BTCUSDT", "15m")

    assert paths.parquet_path == tmp_path / "ohlcv" / "binance" / "BTCUSDT" / "15m.parquet"
    assert paths.metadata_path == tmp_path / "ohlcv" / "binance" / "BTCUSDT" / "15m.metadata.json"


def test_read_parquet_if_exists_returns_none_when_missing(tmp_path) -> None:
    assert read_parquet_if_exists(tmp_path / "missing.parquet") is None


def test_read_metadata_if_exists_returns_none_when_missing(tmp_path) -> None:
    assert read_metadata_if_exists(tmp_path / "missing.metadata.json") is None


def test_atomic_write_creates_parquet_and_metadata(tmp_path) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _df(t0)
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status="complete")

    atomic_write(df, metadata, paths)

    assert paths.parquet_path.exists()
    assert paths.metadata_path.exists()
    assert not paths.parquet_path.with_name(paths.parquet_path.name + ".tmp").exists()
    reloaded = read_parquet_if_exists(paths.parquet_path)
    assert reloaded.height == 1
    reloaded_metadata = read_metadata_if_exists(paths.metadata_path)
    assert reloaded_metadata.status == "complete"
    assert reloaded_metadata.schema_version == 1


def test_atomic_write_failure_preserves_previous_dataset(tmp_path, monkeypatch) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _df(t0)
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status="complete")
    atomic_write(df, metadata, paths)

    original_parquet_bytes = paths.parquet_path.read_bytes()
    original_metadata_text = paths.metadata_path.read_text()

    def _boom(self, *_args, **_kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _boom)

    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    new_df = _df(t0, t1)
    new_metadata = build_metadata(new_df, config, gaps=[], status="complete")

    with pytest.raises(RuntimeError):
        atomic_write(new_df, new_metadata, paths)

    assert paths.parquet_path.read_bytes() == original_parquet_bytes
    assert paths.metadata_path.read_text() == original_metadata_text
    assert not paths.parquet_path.with_name(paths.parquet_path.name + ".tmp").exists()


def test_reconcile_metadata_returns_unchanged_when_matching(tmp_path) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _df(t0)
    metadata = build_metadata(df, config, gaps=[], status="complete")

    reconciled = reconcile_metadata(df, metadata, config)

    assert reconciled == metadata


def test_reconcile_metadata_regenerates_when_parquet_disagrees(tmp_path) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    df = _df(t0, t1)
    stale_metadata = build_metadata(_df(t0), config, gaps=[], status="complete")

    reconciled = reconcile_metadata(df, stale_metadata, config)

    assert reconciled.end == t1
    assert reconciled.row_count == 2

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

import runner.cli as cli_module
from data.config import DownloadConfig
from data.storage import atomic_write, build_metadata, dataset_paths
from runner.cli import main

START = datetime(2020, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _seed_dataset(base_dir: Path, count: int, status: str = "complete") -> None:
    config = DownloadConfig(exchange="binance", symbol="BTC/USDT", timeframe="15m", start=START)
    rows = []
    for i in range(count):
        close = 100.0 + 0.1 * i
        rows.append(
            {
                "timestamp": START + i * INTERVAL, "open": close, "high": close + 0.2,
                "low": close - 0.2, "close": close, "volume": 1.0,
            }
        )
    df = pl.DataFrame(rows)
    paths = dataset_paths(base_dir, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status=status)
    atomic_write(df, metadata, paths)


def test_main_rejects_incomplete_dataset_without_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "reports"
    _seed_dataset(data_dir, 60, status="incomplete")
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", data_dir)

    exit_code = main(["--output-dir", str(output_dir)])

    assert exit_code == 1
    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_main_allows_incomplete_dataset_with_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "reports"
    _seed_dataset(data_dir, 60, status="incomplete")
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", data_dir)

    exit_code = main(["--output-dir", str(output_dir), "--allow-incomplete-dataset"])

    assert exit_code == 0
    run_dirs = list(output_dir.iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "summary.json").exists()
    assert (run_dirs[0] / "trades.csv").exists()
    assert (run_dirs[0] / "equity_curve.parquet").exists()


def test_main_creates_unique_run_directories_across_invocations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "reports"
    _seed_dataset(data_dir, 60, status="complete")
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", data_dir)

    assert main(["--output-dir", str(output_dir)]) == 0
    assert main(["--output-dir", str(output_dir)]) == 0

    run_dirs = list(output_dir.iterdir())
    assert len(run_dirs) == 2
    for run_dir in run_dirs:
        assert (run_dir / "summary.json").exists()
        assert (run_dir / "trades.csv").exists()
        assert (run_dir / "equity_curve.parquet").exists()


def test_main_zero_trade_backtest_still_exports_valid_trades_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "reports"
    # 60 candles is below the strategy's 200-candle warm-up, so
    # generate_signals always returns [] -- a guaranteed zero-trade run.
    _seed_dataset(data_dir, 60, status="complete")
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", data_dir)

    exit_code = main(["--output-dir", str(output_dir)])

    assert exit_code == 0
    run_dir = list(output_dir.iterdir())[0]
    text = (run_dir / "trades.csv").read_text()
    assert len(text.splitlines()) == 1
    assert "signal_id" in text

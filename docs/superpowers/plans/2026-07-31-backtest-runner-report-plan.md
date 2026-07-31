# Backtest Runner and Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing Data Pipeline / Sample Strategy / Backtesting Engine modules into one CLI (`runner/cli.py`) that produces an honest, structured report (`report/builder.py`, `report/export.py`) in a unique directory per run, exactly per `docs/superpowers/specs/2026-07-31-backtest-runner-report-design.md`.

**Architecture:** `report/` (pure calculation + file export, no simulation logic) and `runner/` (thin orchestration CLI: loader -> strategy -> engine -> report). No changes to any existing module.

**Tech Stack:** Python 3.14, Polars, Pydantic v2, pytest. No new dependencies.

## Global Constraints

- Every function has type hints; use `logging`, never `print()`.
- `report/builder.py` and `report/export.py` never import `pathlib` for reading datasets, never call `engine.backtester.run`, and never touch CCXT/network — pure functions over already-computed data.
- No CLI flag for EMA/ATR/R-multiple parameters — those stay fixed inside `strategy.ema_trend_pullback`.
- Every invocation of `runner/cli.py` writes to its own new subdirectory under `--output-dir` — never overwrite a previous run's files.
- A zero-trade `BacktestResult` must still produce a `trades.csv` with the correct header row (achieved via an explicit Polars schema, not schema inference from data).
- Do not run `git commit` unless explicitly asked.

All file paths below are relative to `Trader_v2/`.

---

### Task 1: Report builder (`report/builder.py`)

**Files:**
- Create: `backend/report/__init__.py`
- Create: `backend/report/builder.py`
- Create: `backend/tests/report/__init__.py`
- Test: `backend/tests/report/test_builder.py`

**Interfaces:**
- Consumes: `engine.models.BacktestResult` and its nested types (existing).
- Produces: `report.builder.GapWarning`, `report.builder.ReportSummary` (both `@dataclass(frozen=True)`), `report.builder.build_summary(result: BacktestResult, num_signals: int, symbol: str, timeframe: str, exchange: str) -> ReportSummary`. Consumed directly by Task 3.

- [ ] **Step 1: Scaffold and update package discovery**

Create empty `backend/report/__init__.py`, `backend/tests/report/__init__.py`.
In `backend/pyproject.toml`, change:
```toml
include = ["data*", "risk*", "engine*", "analytics*", "strategy*"]
```
to:
```toml
include = ["data*", "risk*", "engine*", "analytics*", "strategy*", "report*", "runner*"]
```
(`runner*` is added now so Task 3 doesn't need a second `pip install -e`.)
Run (from `backend/`): `./.venv/Scripts/python.exe -m pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing tests**

`backend/tests/report/test_builder.py`:

```python
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from engine.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    DatasetQuality,
    GapRange,
    RejectedSignal,
    Trade,
)
from report.builder import build_summary

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _config(**overrides) -> BacktestConfig:
    kwargs = dict(
        initial_capital=1000.0, leverage=1.0, risk_per_trade_pct=0.01,
        fee_pct=0.001, slippage_pct=0.0005,
    )
    kwargs.update(overrides)
    return BacktestConfig(**kwargs)


def _trade(pnl: float, exit_reason: str, entry_fee: float, exit_fee: float) -> Trade:
    return Trade(
        signal_id="sig", entry_time=T0, entry_price=100.0, exit_time=T0 + INTERVAL,
        exit_price=100.0, direction="long", quantity=1.0, stop_loss_price=95.0,
        take_profit_price=110.0, exit_reason=exit_reason, entry_fee=entry_fee,
        exit_fee=exit_fee, equity_before=1000.0, equity_after=1000.0 + pnl,
        pnl=pnl, pnl_pct=pnl / 100.0, r_multiple=pnl / 10.0,
    )


def _equity_curve() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [T0 + i * INTERVAL for i in range(5)],
            "equity": [1000.0, 1010.0, 990.0, 1030.0, 1030.0],
        }
    )


def _metrics() -> BacktestMetrics:
    return BacktestMetrics(
        total_trades=2, win_rate=0.5, profit_factor=2.5, expectancy=15.0,
        sharpe_ratio=1.2, max_drawdown_pct=0.02, max_consecutive_losses=1,
    )


def test_build_summary_hand_computed_fields() -> None:
    config = _config()
    trades = [
        _trade(50.0, "take_profit", entry_fee=1.0, exit_fee=1.0),
        _trade(-20.0, "stop_loss", entry_fee=1.0, exit_fee=1.0),
    ]
    dataset_quality = DatasetQuality(
        status="complete",
        gaps=[
            GapRange(start=T0 + INTERVAL, end=T0 + 2 * INTERVAL, severity="small"),
            GapRange(start=T0 - 10 * INTERVAL, end=T0 - 5 * INTERVAL, severity="small"),
            GapRange(start=T0 + 3 * INTERVAL, end=T0 + 10 * INTERVAL, severity="medium"),
        ],
    )
    result = BacktestResult(
        config=config, dataset_quality=dataset_quality, trades=trades,
        rejected_signals=[RejectedSignal(signal_id="r1", timestamp=T0, reason="invalid_stop_placement")],
        equity_curve=_equity_curve(), metrics=_metrics(),
    )

    summary = build_summary(result, num_signals=5, symbol="BTC/USDT", timeframe="15m", exchange="binance")

    assert summary.symbol == "BTC/USDT"
    assert summary.dataset_start == T0
    assert summary.dataset_end == T0 + 4 * INTERVAL
    assert summary.dataset_status == "complete"
    assert len(summary.gap_warnings) == 2
    assert summary.num_signals == 5
    assert summary.num_trades == 2
    assert summary.num_rejected_signals == 1
    assert summary.initial_equity == 1000.0
    assert summary.final_equity == 1030.0
    assert summary.net_pnl == pytest.approx(30.0)
    assert summary.return_pct == pytest.approx(3.0)
    assert summary.total_fees_paid == pytest.approx(4.0)
    assert summary.exit_reason_counts == {"take_profit": 1, "stop_loss": 1}
    assert summary.win_rate == 0.5


def test_build_summary_zero_trades() -> None:
    config = _config()
    result = BacktestResult(
        config=config,
        dataset_quality=DatasetQuality(status="complete", gaps=[]),
        trades=[], rejected_signals=[],
        equity_curve=pl.DataFrame({"timestamp": [T0], "equity": [1000.0]}),
        metrics=BacktestMetrics(
            total_trades=0, win_rate=None, profit_factor=None, expectancy=None,
            sharpe_ratio=None, max_drawdown_pct=None, max_consecutive_losses=None,
        ),
    )

    summary = build_summary(result, num_signals=0, symbol="BTC/USDT", timeframe="15m", exchange="binance")

    assert summary.num_trades == 0
    assert summary.total_fees_paid == 0.0
    assert summary.exit_reason_counts == {}
    assert summary.win_rate is None
    assert summary.net_pnl == 0.0
    assert summary.return_pct == 0.0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/report/test_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'report.builder'`

- [ ] **Step 4: Implement the builder**

`backend/report/builder.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engine.models import BacktestConfig, BacktestResult


@dataclass(frozen=True)
class GapWarning:
    start: datetime
    end: datetime
    severity: str


@dataclass(frozen=True)
class ReportSummary:
    symbol: str
    timeframe: str
    exchange: str
    dataset_start: datetime
    dataset_end: datetime
    dataset_status: str
    gap_warnings: list[GapWarning]
    config: BacktestConfig
    num_signals: int
    num_trades: int
    num_rejected_signals: int
    initial_equity: float
    final_equity: float
    net_pnl: float
    return_pct: float
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    max_consecutive_losses: int | None
    total_fees_paid: float
    exit_reason_counts: dict[str, int]


def build_summary(
    result: BacktestResult,
    num_signals: int,
    symbol: str,
    timeframe: str,
    exchange: str,
) -> ReportSummary:
    timestamps = result.equity_curve["timestamp"].to_list()
    equities = result.equity_curve["equity"].to_list()
    dataset_start = timestamps[0]
    dataset_end = timestamps[-1]

    gap_warnings = [
        GapWarning(start=g.start, end=g.end, severity=g.severity)
        for g in result.dataset_quality.gaps
        if g.start <= dataset_end and g.end >= dataset_start
    ]

    initial_equity = result.config.initial_capital
    final_equity = equities[-1]
    net_pnl = final_equity - initial_equity
    return_pct = (net_pnl / initial_equity) * 100

    total_fees_paid = sum(t.entry_fee + t.exit_fee for t in result.trades)

    exit_reason_counts: dict[str, int] = {}
    for trade in result.trades:
        exit_reason_counts[trade.exit_reason] = exit_reason_counts.get(trade.exit_reason, 0) + 1

    metrics = result.metrics

    return ReportSummary(
        symbol=symbol,
        timeframe=timeframe,
        exchange=exchange,
        dataset_start=dataset_start,
        dataset_end=dataset_end,
        dataset_status=result.dataset_quality.status,
        gap_warnings=gap_warnings,
        config=result.config,
        num_signals=num_signals,
        num_trades=len(result.trades),
        num_rejected_signals=len(result.rejected_signals),
        initial_equity=initial_equity,
        final_equity=final_equity,
        net_pnl=net_pnl,
        return_pct=return_pct,
        win_rate=metrics.win_rate,
        profit_factor=metrics.profit_factor,
        expectancy=metrics.expectancy,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown_pct=metrics.max_drawdown_pct,
        max_consecutive_losses=metrics.max_consecutive_losses,
        total_fees_paid=total_fees_paid,
        exit_reason_counts=exit_reason_counts,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/report/test_builder.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/` and confirm the full suite (100 previous + 2 new) passes.

---

### Task 2: Report export (`report/export.py`)

**Files:**
- Create: `backend/report/export.py`
- Test: `backend/tests/report/test_export.py`

**Interfaces:**
- Consumes: `report.builder.ReportSummary` / `GapWarning` (Task 1), `engine.models.Trade` (existing).
- Produces: `report.export.write_summary_json(summary, path)`, `write_trades_csv(trades, path)`, `write_equity_curve_parquet(equity_curve, path)`. Consumed directly by Task 3.

- [ ] **Step 1: Write the failing tests**

`backend/tests/report/test_export.py`:

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from engine.models import BacktestConfig, Trade
from report.builder import GapWarning, ReportSummary
from report.export import write_equity_curve_parquet, write_summary_json, write_trades_csv

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _summary(**overrides) -> ReportSummary:
    config = BacktestConfig(
        initial_capital=1000.0, leverage=1.0, risk_per_trade_pct=0.01,
        fee_pct=0.001, slippage_pct=0.0005,
    )
    kwargs = dict(
        symbol="BTC/USDT", timeframe="15m", exchange="binance",
        dataset_start=T0, dataset_end=T0 + 4 * INTERVAL, dataset_status="complete",
        gap_warnings=[GapWarning(start=T0, end=T0 + INTERVAL, severity="small")],
        config=config, num_signals=3, num_trades=1, num_rejected_signals=0,
        initial_equity=1000.0, final_equity=1050.0, net_pnl=50.0, return_pct=5.0,
        win_rate=1.0, profit_factor=float("inf"), expectancy=50.0, sharpe_ratio=1.5,
        max_drawdown_pct=0.01, max_consecutive_losses=0, total_fees_paid=2.0,
        exit_reason_counts={"take_profit": 1},
    )
    kwargs.update(overrides)
    return ReportSummary(**kwargs)


def test_write_summary_json_round_trips(tmp_path: Path) -> None:
    summary = _summary()
    path = tmp_path / "summary.json"

    write_summary_json(summary, path)

    payload = json.loads(path.read_text())
    assert payload["symbol"] == "BTC/USDT"
    assert payload["profit_factor"] == float("inf")
    assert payload["net_pnl"] == pytest.approx(50.0)
    assert payload["config"]["initial_capital"] == pytest.approx(1000.0)
    assert len(payload["gap_warnings"]) == 1


def test_write_trades_csv_zero_trades_has_correct_header(tmp_path: Path) -> None:
    path = tmp_path / "trades.csv"

    write_trades_csv([], path)

    text = path.read_text()
    lines = text.splitlines()
    assert len(lines) == 1
    for field in ("signal_id", "entry_time", "exit_reason", "pnl", "r_multiple"):
        assert field in lines[0]


def test_write_trades_csv_round_trips_with_data(tmp_path: Path) -> None:
    trade = Trade(
        signal_id="sig-1", entry_time=T0, entry_price=100.0, exit_time=T0 + INTERVAL,
        exit_price=110.0, direction="long", quantity=2.0, stop_loss_price=95.0,
        take_profit_price=110.0, exit_reason="take_profit", entry_fee=0.1, exit_fee=0.1,
        equity_before=1000.0, equity_after=1019.8, pnl=19.8, pnl_pct=0.099, r_multiple=1.98,
    )
    path = tmp_path / "trades.csv"

    write_trades_csv([trade], path)

    df = pl.read_csv(path)
    assert df.height == 1
    assert df["signal_id"][0] == "sig-1"
    assert df["pnl"][0] == pytest.approx(19.8)


def test_write_equity_curve_parquet_round_trips(tmp_path: Path) -> None:
    df = pl.DataFrame({"timestamp": [T0, T0 + INTERVAL], "equity": [1000.0, 1010.0]})
    path = tmp_path / "equity_curve.parquet"

    write_equity_curve_parquet(df, path)

    reloaded = pl.read_parquet(path)
    assert reloaded.height == 2
    assert reloaded["equity"].to_list() == [1000.0, 1010.0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/report/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'report.export'`

- [ ] **Step 3: Implement export**

`backend/report/export.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from engine.models import Trade
from report.builder import ReportSummary

_TRADE_SCHEMA = {
    "signal_id": pl.Utf8,
    "entry_time": pl.Datetime(time_unit="us", time_zone="UTC"),
    "entry_price": pl.Float64,
    "exit_time": pl.Datetime(time_unit="us", time_zone="UTC"),
    "exit_price": pl.Float64,
    "direction": pl.Utf8,
    "quantity": pl.Float64,
    "stop_loss_price": pl.Float64,
    "take_profit_price": pl.Float64,
    "exit_reason": pl.Utf8,
    "entry_fee": pl.Float64,
    "exit_fee": pl.Float64,
    "equity_before": pl.Float64,
    "equity_after": pl.Float64,
    "pnl": pl.Float64,
    "pnl_pct": pl.Float64,
    "r_multiple": pl.Float64,
}


def write_summary_json(summary: ReportSummary, path: Path) -> None:
    payload = {
        "symbol": summary.symbol,
        "timeframe": summary.timeframe,
        "exchange": summary.exchange,
        "dataset_start": summary.dataset_start.isoformat(),
        "dataset_end": summary.dataset_end.isoformat(),
        "dataset_status": summary.dataset_status,
        "gap_warnings": [
            {"start": g.start.isoformat(), "end": g.end.isoformat(), "severity": g.severity}
            for g in summary.gap_warnings
        ],
        "config": summary.config.model_dump(),
        "num_signals": summary.num_signals,
        "num_trades": summary.num_trades,
        "num_rejected_signals": summary.num_rejected_signals,
        "initial_equity": summary.initial_equity,
        "final_equity": summary.final_equity,
        "net_pnl": summary.net_pnl,
        "return_pct": summary.return_pct,
        "win_rate": summary.win_rate,
        "profit_factor": summary.profit_factor,
        "expectancy": summary.expectancy,
        "sharpe_ratio": summary.sharpe_ratio,
        "max_drawdown_pct": summary.max_drawdown_pct,
        "max_consecutive_losses": summary.max_consecutive_losses,
        "total_fees_paid": summary.total_fees_paid,
        "exit_reason_counts": summary.exit_reason_counts,
    }
    path.write_text(json.dumps(payload, indent=2))


def write_trades_csv(trades: list[Trade], path: Path) -> None:
    rows = [
        {
            "signal_id": t.signal_id,
            "entry_time": t.entry_time,
            "entry_price": t.entry_price,
            "exit_time": t.exit_time,
            "exit_price": t.exit_price,
            "direction": t.direction,
            "quantity": t.quantity,
            "stop_loss_price": t.stop_loss_price,
            "take_profit_price": t.take_profit_price,
            "exit_reason": t.exit_reason,
            "entry_fee": t.entry_fee,
            "exit_fee": t.exit_fee,
            "equity_before": t.equity_before,
            "equity_after": t.equity_after,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
            "r_multiple": t.r_multiple,
        }
        for t in trades
    ]
    df = pl.DataFrame(rows, schema=_TRADE_SCHEMA)
    df.write_csv(path)


def write_equity_curve_parquet(equity_curve: pl.DataFrame, path: Path) -> None:
    equity_curve.write_parquet(path)
```

If `pl.DataFrame([], schema=_TRADE_SCHEMA)` does not produce an empty
DataFrame with the correct columns on the installed Polars version, use
`pl.DataFrame({name: [] for name in _TRADE_SCHEMA}, schema=_TRADE_SCHEMA)`
instead — verify with the zero-trades test in Step 5.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/report/test_export.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` and confirm all tests pass.

---

### Task 3: Runner CLI (`runner/cli.py`)

**Files:**
- Create: `backend/runner/__init__.py`
- Create: `backend/runner/cli.py`
- Create: `backend/tests/runner/__init__.py`
- Test: `backend/tests/runner/test_cli.py`

**Interfaces:**
- Consumes: `engine.loader.load_dataset`, `engine.backtester.run`, `engine.models.BacktestConfig`, `data.exceptions.DataIntegrityError`, `strategy.ema_trend_pullback.generate_signals`, `report.builder.build_summary`, `report.export.*` (all existing/Tasks 1-2).
- Produces: `runner.cli.build_parser() -> argparse.ArgumentParser`, `runner.cli.main(argv=None) -> int`, module-level `runner.cli.DEFAULT_DATA_DIR: Path` and `runner.cli.DEFAULT_OUTPUT_DIR: Path`.

- [ ] **Step 1: Scaffold**

Create empty `backend/runner/__init__.py`, `backend/tests/runner/__init__.py`.
(`runner*` was already added to `pyproject.toml`'s package discovery in
Task 1, Step 1 — no reinstall needed here unless it was skipped.)

- [ ] **Step 2: Write the failing tests**

`backend/tests/runner/test_cli.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/runner/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'runner.cli'`

- [ ] **Step 4: Implement the CLI**

`backend/runner/cli.py`:

```python
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from data.exceptions import DataIntegrityError
from engine.backtester import run
from engine.loader import load_dataset
from engine.models import BacktestConfig
from report.builder import build_summary
from report.export import write_equity_curve_parquet, write_summary_json, write_trades_csv
from strategy.ema_trend_pullback import generate_signals

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "reports"


def _create_run_directory(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    run_dir = base_dir / f"run_{timestamp}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.runner.cli")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--allow-incomplete-dataset", action="store_true")
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    parser.add_argument("--fee-pct", type=float, default=0.001)
    parser.add_argument("--slippage-pct", type=float, default=0.0005)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    parser = build_parser()
    args = parser.parse_args(argv)

    symbol_slug = args.symbol.replace("/", "")

    try:
        ohlcv, dataset_quality = load_dataset(DEFAULT_DATA_DIR, args.exchange, symbol_slug, args.timeframe)
    except FileNotFoundError as error:
        logger.error("Dataset load failed: %s", error)
        return 1

    config = BacktestConfig(
        initial_capital=args.initial_capital,
        leverage=args.leverage,
        risk_per_trade_pct=args.risk_per_trade_pct,
        fee_pct=args.fee_pct,
        slippage_pct=args.slippage_pct,
        allow_incomplete_dataset=args.allow_incomplete_dataset,
    )

    signals = generate_signals(ohlcv)

    try:
        result = run(ohlcv, signals, dataset_quality, config)
    except DataIntegrityError as error:
        logger.error("Backtest aborted: %s", error)
        return 1

    summary = build_summary(result, len(signals), args.symbol, args.timeframe, args.exchange)

    run_dir = _create_run_directory(args.output_dir)
    write_summary_json(summary, run_dir / "summary.json")
    write_trades_csv(result.trades, run_dir / "trades.csv")
    write_equity_curve_parquet(result.equity_curve, run_dir / "equity_curve.parquet")

    logger.info("Report written to %s", run_dir)
    logger.info(
        "Signals=%d Trades=%d Rejected=%d NetPnL=%.2f Return=%.2f%% WinRate=%s",
        summary.num_signals, summary.num_trades, summary.num_rejected_signals,
        summary.net_pnl, summary.return_pct, summary.win_rate,
    )
    logger.info("This is a hypothesis test only -- not a profitability claim.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/runner/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/` and confirm the full suite (100 + 2 + 4 + 4 = 110) passes.

---

### Task 4: Module READMEs

**Files:**
- Create: `backend/report/README.md`
- Create: `backend/runner/README.md`

- [ ] **Step 1: Write `backend/report/README.md`**

```markdown
# report — Backtest Report Builder and Export

Pure reporting logic, no simulation code. Consumes `engine.models.BacktestResult`.

- `builder.py` — `build_summary(result, num_signals, symbol, timeframe, exchange) -> ReportSummary`.
  Computes dataset range/quality, gap-overlap warnings, equity/PnL,
  fee totals, exit-reason counts. Read-only over `BacktestResult` — never
  calls the simulation engine.
- `export.py` — `write_summary_json`, `write_trades_csv` (explicit schema,
  so a zero-trade result still writes a correctly-headered CSV),
  `write_equity_curve_parquet`.

See `docs/superpowers/specs/2026-07-31-backtest-runner-report-design.md`.
```

- [ ] **Step 2: Write `backend/runner/README.md`**

```markdown
# runner — Backtest Runner CLI

Orchestration only: `engine.loader` -> `strategy.ema_trend_pullback` ->
`engine.backtester` -> `report`. No simulation or report-calculation logic
lives here.

```
python -m backend.runner.cli \
  --symbol BTC/USDT --timeframe 15m --exchange binance \
  --output-dir ./reports \
  [--allow-incomplete-dataset] \
  [--initial-capital 10000] [--leverage 1.0] \
  [--risk-per-trade-pct 0.005] [--fee-pct 0.001] [--slippage-pct 0.0005]
```

Every run writes to a new `run_<timestamp>_<uuid8>/` subdirectory under
`--output-dir` — previous reports are never overwritten. No flags exist for
EMA/ATR/R-multiple — those are fixed inside the strategy module.

See `docs/superpowers/specs/2026-07-31-backtest-runner-report-design.md`.
```

- [ ] **Step 3: Checkpoint**

Confirm both README files render correctly. No test changes in this task.

---

## Final Verification

- [ ] Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/`
  one more time and confirm the entire suite passes.
- [ ] Run the CLI against the real BTC/USDT dataset without
  `--allow-incomplete-dataset` — confirm it refuses (dataset status is
  currently `incomplete`).
- [ ] Run the CLI against the real BTC/USDT dataset with
  `--allow-incomplete-dataset` — confirm a report is produced, inspect
  `summary.json`, and present the result with no profitability claims.
- [ ] Confirm no `git commit` was run unless explicitly requested.

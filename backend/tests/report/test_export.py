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

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

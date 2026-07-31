from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from analytics.metrics import compute_metrics
from engine.models import Trade

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _trade(pnl: float, index: int) -> Trade:
    t = START + index * INTERVAL
    return Trade(
        signal_id=f"s{index}",
        entry_time=t,
        entry_price=100.0,
        exit_time=t,
        exit_price=100.0,
        direction="long",
        quantity=1.0,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        exit_reason="take_profit" if pnl > 0 else "stop_loss",
        entry_fee=0.0,
        exit_fee=0.0,
        equity_before=1000.0,
        equity_after=1000.0 + pnl,
        pnl=pnl,
        pnl_pct=pnl / 100.0,
        r_multiple=pnl / 10.0,
    )


def _equity_curve(values: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * INTERVAL for i in range(len(values))],
            "equity": values,
        }
    )


def test_compute_metrics_returns_none_for_zero_trades() -> None:
    metrics = compute_metrics([], _equity_curve([1000.0]), 35040)

    assert metrics.total_trades == 0
    assert metrics.win_rate is None
    assert metrics.profit_factor is None
    assert metrics.expectancy is None
    assert metrics.sharpe_ratio is None
    assert metrics.max_drawdown_pct is None
    assert metrics.max_consecutive_losses is None


def test_compute_metrics_win_rate_and_expectancy() -> None:
    trades = [_trade(100.0, 0), _trade(-50.0, 1), _trade(200.0, 2), _trade(-50.0, 3)]
    equity_curve = _equity_curve([1000.0, 1100.0, 1050.0, 1250.0, 1200.0])

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.total_trades == 4
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.expectancy == pytest.approx((100 - 50 + 200 - 50) / 4)


def test_compute_metrics_profit_factor_is_inf_with_no_losses() -> None:
    trades = [_trade(100.0, 0), _trade(50.0, 1)]
    equity_curve = _equity_curve([1000.0, 1100.0, 1150.0])

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.profit_factor == float("inf")


def test_compute_metrics_profit_factor_hand_computed() -> None:
    trades = [_trade(300.0, 0), _trade(-100.0, 1), _trade(-50.0, 2)]
    equity_curve = _equity_curve([1000.0, 1300.0, 1200.0, 1150.0])

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.profit_factor == pytest.approx(300 / 150)


def test_compute_metrics_max_drawdown_hand_computed() -> None:
    equity_curve = _equity_curve([1000.0, 1200.0, 900.0, 950.0, 1300.0, 1100.0])

    metrics = compute_metrics([_trade(100.0, 0)], equity_curve, 35040)

    assert metrics.max_drawdown_pct == pytest.approx(0.25)


def test_compute_metrics_max_consecutive_losses_hand_computed() -> None:
    trades = [
        _trade(10.0, 0), _trade(-5.0, 1), _trade(-5.0, 2),
        _trade(-5.0, 3), _trade(10.0, 4), _trade(-1.0, 5),
    ]
    equity_curve = _equity_curve([1000.0] * 7)

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.max_consecutive_losses == 3


def test_compute_metrics_sharpe_ratio_zero_when_no_variance() -> None:
    equity_curve = _equity_curve([1000.0, 1000.0, 1000.0, 1000.0])

    metrics = compute_metrics([_trade(0.0, 0)], equity_curve, 35040)

    assert metrics.sharpe_ratio == 0.0


def test_compute_metrics_sharpe_ratio_matches_documented_formula() -> None:
    values = [1000.0, 1010.0, 1005.0, 1030.0, 1020.0]
    equity_curve = _equity_curve(values)

    metrics = compute_metrics([_trade(20.0, 0)], equity_curve, 35040)

    returns = [(values[i] / values[i - 1]) - 1 for i in range(1, len(values))]
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    std_r = variance ** 0.5
    expected_sharpe = (mean_r / std_r) * (35040 ** 0.5)

    assert metrics.sharpe_ratio == pytest.approx(expected_sharpe)

from __future__ import annotations

import math

import polars as pl

from engine.models import BacktestMetrics, Trade


def compute_metrics(
    trades: list[Trade],
    equity_curve: pl.DataFrame,
    candles_per_year: int,
) -> BacktestMetrics:
    total_trades = len(trades)
    if total_trades == 0:
        return BacktestMetrics(
            total_trades=0,
            win_rate=None,
            profit_factor=None,
            expectancy=None,
            sharpe_ratio=None,
            max_drawdown_pct=None,
            max_consecutive_losses=None,
        )

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / total_trades
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = float("inf") if gross_loss == 0 else gross_profit / gross_loss
    expectancy = sum(pnls) / total_trades

    return BacktestMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        sharpe_ratio=_sharpe_ratio(equity_curve, candles_per_year),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        max_consecutive_losses=_max_consecutive_losses(pnls),
    )


def _sharpe_ratio(equity_curve: pl.DataFrame, candles_per_year: int) -> float:
    equity = equity_curve["equity"].to_list()
    if len(equity) < 2:
        return 0.0
    returns = [
        (equity[i] / equity[i - 1]) - 1
        for i in range(1, len(equity))
        if equity[i - 1] != 0
    ]
    if len(returns) < 2:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = math.sqrt(variance)
    if std_return == 0:
        return 0.0
    return (mean_return / std_return) * math.sqrt(candles_per_year)


def _max_drawdown_pct(equity_curve: pl.DataFrame) -> float:
    equity = equity_curve["equity"].to_list()
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def _max_consecutive_losses(pnls: list[float]) -> int:
    longest = 0
    current = 0
    for pnl in pnls:
        if pnl <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest

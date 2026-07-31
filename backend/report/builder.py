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

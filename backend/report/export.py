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

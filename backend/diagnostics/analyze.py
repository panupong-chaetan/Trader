"""Read-only diagnostics over an existing backtest report.

Consumes summary.json / trades.csv / equity_curve.parquet produced by
runner.cli, plus a read-only re-derivation of the strategy's raw signal
list (strategy.ema_trend_pullback.generate_signals is a pure function --
calling it again does not modify the strategy or the engine). Never calls
engine.backtester.run and never writes to the dataset or the run
directory it reads from.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import polars as pl

from engine.loader import load_dataset
from strategy.ema_trend_pullback import generate_signals

INTERVAL = timedelta(minutes=15)


def load_report(run_dir: Path) -> tuple[dict, pl.DataFrame, pl.DataFrame]:
    summary = json.loads((run_dir / "summary.json").read_text())
    trades = pl.read_csv(run_dir / "trades.csv", try_parse_dates=True)
    equity_curve = pl.read_parquet(run_dir / "equity_curve.parquet")
    return summary, trades, equity_curve


def performance_by_period(trades: pl.DataFrame, period: str) -> pl.DataFrame:
    col = trades["entry_time"].dt.year() if period == "year" else trades["entry_time"].dt.strftime("%Y-%m")
    return (
        trades.with_columns(col.alias("period"))
        .group_by("period")
        .agg(
            pl.len().alias("trades"),
            (pl.col("pnl") > 0).sum().alias("wins"),
            pl.col("pnl").sum().alias("net_pnl"),
            (pl.col("entry_fee") + pl.col("exit_fee")).sum().alias("fees"),
        )
        .with_columns((pl.col("wins") / pl.col("trades")).alias("win_rate"))
        .sort("period")
    )


def performance_by_direction(trades: pl.DataFrame) -> pl.DataFrame:
    return (
        trades.group_by("direction")
        .agg(
            pl.len().alias("trades"),
            (pl.col("pnl") > 0).sum().alias("wins"),
            pl.col("pnl").sum().alias("net_pnl"),
            pl.col("pnl").mean().alias("avg_pnl"),
        )
        .with_columns((pl.col("wins") / pl.col("trades")).alias("win_rate"))
        .sort("direction")
    )


def performance_by_exit_reason(trades: pl.DataFrame) -> pl.DataFrame:
    return (
        trades.group_by("exit_reason")
        .agg(
            pl.len().alias("trades"),
            pl.col("pnl").sum().alias("net_pnl"),
            pl.col("pnl").mean().alias("avg_pnl"),
            pl.col("r_multiple").mean().alias("avg_r_multiple"),
        )
        .sort("exit_reason")
    )


def trade_duration_stats(trades: pl.DataFrame) -> dict:
    duration_minutes = (trades["exit_time"] - trades["entry_time"]).dt.total_minutes()
    return {
        "mean_minutes": duration_minutes.mean(),
        "median_minutes": duration_minutes.median(),
        "min_minutes": duration_minutes.min(),
        "max_minutes": duration_minutes.max(),
    }


def fee_impact(trades: pl.DataFrame) -> dict:
    total_fees = (trades["entry_fee"] + trades["exit_fee"]).sum()
    net_pnl = trades["pnl"].sum()
    gross_pnl = net_pnl + total_fees
    return {
        "gross_pnl": gross_pnl,
        "total_fees": total_fees,
        "net_pnl": net_pnl,
        "fee_drag_pct_of_gross_loss": (total_fees / abs(gross_pnl) * 100) if gross_pnl != 0 else None,
    }


def consecutive_loss_streaks(trades: pl.DataFrame) -> dict[int, int]:
    streaks: dict[int, int] = {}
    current = 0
    for pnl in trades["pnl"].to_list():
        if pnl <= 0:
            current += 1
        else:
            if current > 0:
                streaks[current] = streaks.get(current, 0) + 1
            current = 0
    if current > 0:
        streaks[current] = streaks.get(current, 0) + 1
    return dict(sorted(streaks.items()))


def drawdown_episodes(equity_curve: pl.DataFrame, top_n: int = 5) -> list[dict]:
    timestamps = equity_curve["timestamp"].to_list()
    equities = equity_curve["equity"].to_list()

    episodes = []
    peak = equities[0]
    peak_time = timestamps[0]
    in_drawdown = False
    trough = equities[0]
    trough_time = timestamps[0]

    for ts, eq in zip(timestamps, equities):
        if eq >= peak:
            if in_drawdown:
                episodes.append(
                    {
                        "peak_time": peak_time,
                        "peak_equity": peak,
                        "trough_time": trough_time,
                        "trough_equity": trough,
                        "drawdown_pct": (peak - trough) / peak * 100 if peak > 0 else None,
                        "recovery_time": ts,
                    }
                )
                in_drawdown = False
            peak = eq
            peak_time = ts
            trough = eq
            trough_time = ts
        else:
            in_drawdown = True
            if eq < trough:
                trough = eq
                trough_time = ts

    if in_drawdown:
        episodes.append(
            {
                "peak_time": peak_time,
                "peak_equity": peak,
                "trough_time": trough_time,
                "trough_equity": trough,
                "drawdown_pct": (peak - trough) / peak * 100 if peak > 0 else None,
                "recovery_time": None,
            }
        )

    episodes.sort(key=lambda e: e["drawdown_pct"] or 0, reverse=True)
    return episodes[:top_n]


def signal_frequency(all_signals: list, trades: pl.DataFrame) -> dict:
    # trades.csv's signal_id is the originating signal's timestamp
    # (Signal.signal_id == timestamp.isoformat()); when read with
    # try_parse_dates=True, Polars auto-converts that column to datetime,
    # so compare against Signal.timestamp directly rather than strings.
    executed_timestamps = set(trades["signal_id"].to_list())
    total = len(all_signals)
    executed = sum(1 for s in all_signals if s.timestamp in executed_timestamps)
    skipped_in_position = total - executed
    return {
        "total_signals": total,
        "executed": executed,
        "skipped_while_in_position": skipped_in_position,
        "skip_rate_pct": (skipped_in_position / total * 100) if total else None,
    }


def gap_adjacent_trades(trades: pl.DataFrame, gaps: list[dict], window_days: int = 3) -> pl.DataFrame:
    from datetime import datetime, timezone

    rows = []
    for gap in gaps:
        gap_start = datetime.fromisoformat(gap["start"])
        gap_end = datetime.fromisoformat(gap["end"])
        window_start = gap_start - timedelta(days=window_days)
        window_end = gap_end + timedelta(days=window_days)
        nearby = trades.filter(
            (pl.col("entry_time") >= window_start) & (pl.col("entry_time") <= window_end)
        )
        rows.append(
            {
                "gap_start": gap["start"],
                "severity": gap["severity"],
                "trades_nearby": nearby.height,
                "net_pnl_nearby": nearby["pnl"].sum() if nearby.height else 0.0,
            }
        )
    return pl.DataFrame(rows)


def yearly_price_regime(ohlcv: pl.DataFrame) -> pl.DataFrame:
    return (
        ohlcv.with_columns(pl.col("timestamp").dt.year().alias("year"))
        .group_by("year")
        .agg(pl.col("close").first().alias("open_price"), pl.col("close").last().alias("close_price"))
        .with_columns(
            ((pl.col("close_price") - pl.col("open_price")) / pl.col("open_price") * 100).alias("price_change_pct")
        )
        .sort("year")
    )

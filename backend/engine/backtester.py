from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import polars as pl

from analytics.metrics import compute_metrics
from data.exceptions import DataIntegrityError
from engine.models import (
    BacktestConfig,
    BacktestResult,
    DatasetQuality,
    RejectedSignal,
    Signal,
    Trade,
)
from risk.sizing import size_position

logger = logging.getLogger(__name__)


def _entry_fill_price(direction: str, open_price: float, slippage_pct: float) -> float:
    if direction == "long":
        return open_price * (1 + slippage_pct)
    return open_price * (1 - slippage_pct)


def _exit_fill_price(direction: str, raw_price: float, slippage_pct: float) -> float:
    if direction == "long":
        return raw_price * (1 - slippage_pct)
    return raw_price * (1 + slippage_pct)


@dataclass(frozen=True)
class TouchResult:
    exit_reason: str | None
    raw_exit_price: float | None


def _resolve_touch(
    direction: str,
    low: float,
    high: float,
    stop_loss_price: float,
    take_profit_price: float,
) -> TouchResult:
    if direction == "long":
        sl_touched = low <= stop_loss_price
        tp_touched = high >= take_profit_price
    else:
        sl_touched = high >= stop_loss_price
        tp_touched = low <= take_profit_price

    if sl_touched:
        return TouchResult(exit_reason="stop_loss", raw_exit_price=stop_loss_price)
    if tp_touched:
        return TouchResult(exit_reason="take_profit", raw_exit_price=take_profit_price)
    return TouchResult(exit_reason=None, raw_exit_price=None)


def _resolve_gap_through(
    direction: str,
    open_price: float,
    stop_loss_price: float,
    take_profit_price: float,
) -> TouchResult:
    if direction == "long":
        sl_gapped = open_price <= stop_loss_price
        tp_gapped = open_price >= take_profit_price
    else:
        sl_gapped = open_price >= stop_loss_price
        tp_gapped = open_price <= take_profit_price

    if sl_gapped:
        return TouchResult(exit_reason="stop_loss", raw_exit_price=open_price)
    if tp_gapped:
        return TouchResult(exit_reason="take_profit", raw_exit_price=open_price)
    return TouchResult(exit_reason=None, raw_exit_price=None)


@dataclass
class _OpenPosition:
    signal_id: str
    direction: str
    entry_time: datetime
    entry_price: float
    quantity: float
    stop_loss_price: float
    take_profit_price: float
    entry_fee: float
    equity_before: float


def _unrealized_gross_pnl(position: _OpenPosition, mark_price: float) -> float:
    if position.direction == "long":
        return (mark_price - position.entry_price) * position.quantity
    return (position.entry_price - mark_price) * position.quantity


def _try_open_position(
    signal: Signal,
    row: dict,
    equity_at_entry: float,
    config: BacktestConfig,
) -> tuple[_OpenPosition | None, RejectedSignal | None]:
    entry_price_filled = _entry_fill_price(signal.direction, row["open"], config.slippage_pct)
    sizing = size_position(signal.direction, entry_price_filled, signal.stop_loss_price, equity_at_entry, config)

    if not sizing.accepted:
        return None, RejectedSignal(signal_id=signal.signal_id, timestamp=row["timestamp"], reason=sizing.reason)

    entry_fee = entry_price_filled * sizing.quantity * config.fee_pct
    position = _OpenPosition(
        signal_id=signal.signal_id,
        direction=signal.direction,
        entry_time=row["timestamp"],
        entry_price=entry_price_filled,
        quantity=sizing.quantity,
        stop_loss_price=signal.stop_loss_price,
        take_profit_price=signal.take_profit_price,
        entry_fee=entry_fee,
        equity_before=equity_at_entry,
    )
    return position, None


def _close_position(
    position: _OpenPosition,
    exit_time: datetime,
    raw_exit_price: float,
    exit_reason: str,
    config: BacktestConfig,
) -> Trade:
    exit_price = _exit_fill_price(position.direction, raw_exit_price, config.slippage_pct)
    exit_fee = exit_price * position.quantity * config.fee_pct

    if position.direction == "long":
        gross_pnl = (exit_price - position.entry_price) * position.quantity
    else:
        gross_pnl = (position.entry_price - exit_price) * position.quantity

    pnl = gross_pnl - position.entry_fee - exit_fee
    equity_after = position.equity_before + pnl
    pnl_pct = pnl / (position.entry_price * position.quantity)
    risked_amount = position.equity_before * config.risk_per_trade_pct
    r_multiple = pnl / risked_amount if risked_amount != 0 else 0.0

    return Trade(
        signal_id=position.signal_id,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        exit_time=exit_time,
        exit_price=exit_price,
        direction=position.direction,
        quantity=position.quantity,
        stop_loss_price=position.stop_loss_price,
        take_profit_price=position.take_profit_price,
        exit_reason=exit_reason,
        entry_fee=position.entry_fee,
        exit_fee=exit_fee,
        equity_before=position.equity_before,
        equity_after=equity_after,
        pnl=pnl,
        pnl_pct=pnl_pct,
        r_multiple=r_multiple,
    )


def run(
    ohlcv: pl.DataFrame,
    signals: list[Signal],
    dataset_quality: DatasetQuality,
    config: BacktestConfig,
) -> BacktestResult:
    if dataset_quality.status == "incomplete" and not config.allow_incomplete_dataset:
        raise DataIntegrityError(
            "Dataset is incomplete; set allow_incomplete_dataset=True to proceed"
        )

    rows = ohlcv.to_dicts()
    _warn_on_overlapping_gaps(rows, dataset_quality)
    signal_by_entry_index = _map_signals_to_entry_rows(rows, signals)

    equity = config.initial_capital
    position: _OpenPosition | None = None
    trades: list[Trade] = []
    rejected_signals: list[RejectedSignal] = []
    equity_curve_rows: list[dict] = []

    for i, row in enumerate(rows):
        exited_this_candle = False

        if position is not None:
            touch = _evaluate_exit(position, row)
            if touch.exit_reason is not None:
                trade = _close_position(position, row["timestamp"], touch.raw_exit_price, touch.exit_reason, config)
                trades.append(trade)
                equity = trade.equity_after
                position = None
                exited_this_candle = True

        if position is None and not exited_this_candle:
            signal = signal_by_entry_index.get(i)
            if signal is not None:
                candidate, rejection = _try_open_position(signal, row, equity, config)
                if rejection is not None:
                    rejected_signals.append(rejection)
                else:
                    position = candidate
                    touch = _evaluate_exit(position, row)
                    if touch.exit_reason is not None:
                        trade = _close_position(position, row["timestamp"], touch.raw_exit_price, touch.exit_reason, config)
                        trades.append(trade)
                        equity = trade.equity_after
                        position = None

        if position is not None:
            unrealized = _unrealized_gross_pnl(position, row["close"])
            curve_equity = equity - position.entry_fee + unrealized
        else:
            curve_equity = equity
        equity_curve_rows.append({"timestamp": row["timestamp"], "equity": curve_equity})

    if position is not None:
        last_row = rows[-1]
        trade = _close_position(position, last_row["timestamp"], last_row["close"], "end_of_data", config)
        trades.append(trade)
        equity = trade.equity_after
        equity_curve_rows[-1] = {"timestamp": last_row["timestamp"], "equity": equity}

    equity_curve = (
        pl.DataFrame(equity_curve_rows)
        if equity_curve_rows
        else pl.DataFrame({"timestamp": [], "equity": []})
    )
    candles_per_year = _infer_candles_per_year(rows)
    metrics = compute_metrics(trades, equity_curve, candles_per_year)

    return BacktestResult(
        config=config,
        dataset_quality=dataset_quality,
        trades=trades,
        rejected_signals=rejected_signals,
        equity_curve=equity_curve,
        metrics=metrics,
    )


def _evaluate_exit(position: _OpenPosition, row: dict) -> TouchResult:
    gap_result = _resolve_gap_through(
        position.direction, row["open"], position.stop_loss_price, position.take_profit_price
    )
    if gap_result.exit_reason is not None:
        return gap_result
    return _resolve_touch(
        position.direction, row["low"], row["high"], position.stop_loss_price, position.take_profit_price
    )


def _map_signals_to_entry_rows(rows: list[dict], signals: list[Signal]) -> dict[int, Signal]:
    timestamp_to_index = {row["timestamp"]: i for i, row in enumerate(rows)}
    mapping: dict[int, Signal] = {}
    for signal in signals:
        signal_row_index = timestamp_to_index.get(signal.timestamp)
        if signal_row_index is None:
            continue
        entry_index = signal_row_index + 1
        if entry_index >= len(rows):
            continue
        mapping.setdefault(entry_index, signal)
    return mapping


def _warn_on_overlapping_gaps(rows: list[dict], dataset_quality: DatasetQuality) -> None:
    if not rows:
        return
    start_ts = rows[0]["timestamp"]
    end_ts = rows[-1]["timestamp"]
    for gap in dataset_quality.gaps:
        if gap.start <= end_ts and gap.end >= start_ts:
            logger.warning(
                "Backtest range overlaps a %s gap between %s and %s",
                gap.severity, gap.start, gap.end,
            )


def _infer_candles_per_year(rows: list[dict]) -> int:
    if len(rows) < 2:
        return 0
    diffs = sorted(
        (rows[i]["timestamp"] - rows[i - 1]["timestamp"]).total_seconds()
        for i in range(1, len(rows))
    )
    median_seconds = diffs[len(diffs) // 2]
    if median_seconds <= 0:
        return 0
    return round((365 * 24 * 3600) / median_seconds)

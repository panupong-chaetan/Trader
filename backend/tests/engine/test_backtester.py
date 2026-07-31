from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from data.exceptions import DataIntegrityError
from engine.backtester import (
    _OpenPosition,
    _close_position,
    _entry_fill_price,
    _exit_fill_price,
    _resolve_gap_through,
    _resolve_touch,
    _try_open_position,
    _unrealized_gross_pnl,
    run,
)
from engine.models import BacktestConfig, DatasetQuality, GapRange, Signal
from risk.sizing import size_position

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _config(**overrides) -> BacktestConfig:
    kwargs = dict(
        initial_capital=10000.0,
        leverage=1.0,
        risk_per_trade_pct=0.01,
        fee_pct=0.001,
        slippage_pct=0.0005,
    )
    kwargs.update(overrides)
    return BacktestConfig(**kwargs)


def test_entry_fill_price_long_slips_up() -> None:
    assert _entry_fill_price("long", 100.0, 0.001) == pytest.approx(100.1)


def test_entry_fill_price_short_slips_down() -> None:
    assert _entry_fill_price("short", 100.0, 0.001) == pytest.approx(99.9)


def test_exit_fill_price_long_slips_down() -> None:
    assert _exit_fill_price("long", 100.0, 0.001) == pytest.approx(99.9)


def test_exit_fill_price_short_slips_up() -> None:
    assert _exit_fill_price("short", 100.0, 0.001) == pytest.approx(100.1)


def test_resolve_touch_long_stop_only() -> None:
    result = _resolve_touch("long", low=94.0, high=101.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason == "stop_loss"
    assert result.raw_exit_price == 95.0


def test_resolve_touch_long_take_profit_only() -> None:
    result = _resolve_touch("long", low=99.0, high=111.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason == "take_profit"
    assert result.raw_exit_price == 110.0


def test_resolve_touch_long_both_touched_prefers_stop_loss() -> None:
    result = _resolve_touch("long", low=90.0, high=120.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason == "stop_loss"


def test_resolve_touch_long_neither_touched() -> None:
    result = _resolve_touch("long", low=96.0, high=105.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason is None
    assert result.raw_exit_price is None


def test_resolve_touch_short_stop_only() -> None:
    result = _resolve_touch("short", low=94.0, high=106.0, stop_loss_price=105.0, take_profit_price=90.0)

    assert result.exit_reason == "stop_loss"
    assert result.raw_exit_price == 105.0


def test_resolve_touch_short_both_touched_prefers_stop_loss() -> None:
    result = _resolve_touch("short", low=85.0, high=110.0, stop_loss_price=105.0, take_profit_price=90.0)

    assert result.exit_reason == "stop_loss"


def test_resolve_gap_through_long_stop_gapped() -> None:
    result = _resolve_gap_through("long", open_price=90.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason == "stop_loss"
    assert result.raw_exit_price == 90.0


def test_resolve_gap_through_long_take_profit_gapped() -> None:
    result = _resolve_gap_through("long", open_price=115.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason == "take_profit"
    assert result.raw_exit_price == 115.0


def test_resolve_gap_through_long_no_gap() -> None:
    result = _resolve_gap_through("long", open_price=100.0, stop_loss_price=95.0, take_profit_price=110.0)

    assert result.exit_reason is None


def test_resolve_gap_through_short_stop_gapped() -> None:
    result = _resolve_gap_through("short", open_price=106.0, stop_loss_price=105.0, take_profit_price=90.0)

    assert result.exit_reason == "stop_loss"
    assert result.raw_exit_price == 106.0


def test_try_open_position_accepts_valid_long_signal() -> None:
    config = _config()
    signal = Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)
    row = {"timestamp": T0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}

    position, rejection = _try_open_position(signal, row, 10000.0, config)

    assert rejection is None
    assert position is not None
    assert position.signal_id == "sig-1"
    assert position.direction == "long"
    assert position.entry_price == pytest.approx(100.0 * 1.0005)
    assert position.quantity > 0


def test_try_open_position_propagates_sizing_rejection() -> None:
    config = _config()
    signal = Signal(signal_id="sig-2", timestamp=T0, direction="long", stop_loss_price=105.0, take_profit_price=110.0)
    row = {"timestamp": T0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}

    position, rejection = _try_open_position(signal, row, 10000.0, config)

    assert position is None
    assert rejection is not None
    assert rejection.signal_id == "sig-2"
    assert rejection.timestamp == T0
    assert rejection.reason == "invalid_stop_placement"


def test_close_position_long_hand_computed_pnl() -> None:
    config = _config(fee_pct=0.001, slippage_pct=0.0005)
    position = _OpenPosition(
        signal_id="sig-1",
        direction="long",
        entry_time=T0,
        entry_price=100.05,
        quantity=10.0,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        entry_fee=100.05 * 10.0 * 0.001,
        equity_before=10000.0,
    )

    trade = _close_position(position, T0, 110.0, "take_profit", config)

    expected_exit_price = 110.0 * (1 - config.slippage_pct)
    expected_exit_fee = expected_exit_price * 10.0 * config.fee_pct
    expected_gross_pnl = (expected_exit_price - position.entry_price) * 10.0
    expected_pnl = expected_gross_pnl - position.entry_fee - expected_exit_fee

    assert trade.exit_price == pytest.approx(expected_exit_price)
    assert trade.exit_fee == pytest.approx(expected_exit_fee)
    assert trade.pnl == pytest.approx(expected_pnl)
    assert trade.equity_after == pytest.approx(position.equity_before + expected_pnl)
    assert trade.pnl_pct == pytest.approx(expected_pnl / (position.entry_price * 10.0))


def test_close_position_r_multiple_is_approximately_minus_one_at_stop() -> None:
    config = _config(risk_per_trade_pct=0.01, fee_pct=0.001, slippage_pct=0.0005)
    entry_price_filled = _entry_fill_price("long", 100.0, config.slippage_pct)

    sizing = size_position("long", entry_price_filled, 95.0, 10000.0, config)
    position = _OpenPosition(
        signal_id="sig-1",
        direction="long",
        entry_time=T0,
        entry_price=entry_price_filled,
        quantity=sizing.quantity,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        entry_fee=entry_price_filled * sizing.quantity * config.fee_pct,
        equity_before=10000.0,
    )

    trade = _close_position(position, T0, 95.0, "stop_loss", config)

    assert trade.r_multiple == pytest.approx(-1.0, abs=1e-6)


def test_unrealized_gross_pnl_long() -> None:
    position = _OpenPosition(
        signal_id="sig-1", direction="long", entry_time=T0, entry_price=100.0,
        quantity=5.0, stop_loss_price=95.0, take_profit_price=110.0,
        entry_fee=0.0, equity_before=10000.0,
    )

    assert _unrealized_gross_pnl(position, 103.0) == pytest.approx(15.0)


def test_unrealized_gross_pnl_short() -> None:
    position = _OpenPosition(
        signal_id="sig-1", direction="short", entry_time=T0, entry_price=100.0,
        quantity=5.0, stop_loss_price=105.0, take_profit_price=90.0,
        entry_fee=0.0, equity_before=10000.0,
    )

    assert _unrealized_gross_pnl(position, 97.0) == pytest.approx(15.0)


def _row(ts, o, h, l, c) -> dict:
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


def _ohlcv(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def _quality(status: str = "complete", gaps: list[GapRange] | None = None) -> DatasetQuality:
    return DatasetQuality(status=status, gaps=gaps or [])


def test_run_enters_long_at_next_candle_open_and_hits_take_profit() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 111.0, 99.0, 105.0),
        _row(T0 + 2 * INTERVAL, 105.0, 106.0, 104.0, 105.5),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == T0 + INTERVAL
    assert trade.exit_reason == "take_profit"
    assert trade.exit_time == T0 + INTERVAL
    assert not result.rejected_signals


def test_run_enters_short_and_hits_stop_loss() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 106.0, 99.0, 101.0),
        _row(T0 + 2 * INTERVAL, 101.0, 102.0, 100.0, 101.5),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="short", stop_loss_price=105.0, take_profit_price=90.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].direction == "short"


def test_run_both_touched_on_entry_candle_prefers_stop_loss() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 111.0, 94.0, 100.0),
        _row(T0 + 2 * INTERVAL, 100.0, 101.0, 99.0, 100.5),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].entry_time == T0 + INTERVAL
    assert result.trades[0].exit_time == T0 + INTERVAL


def test_run_both_touched_on_later_candle_prefers_stop_loss() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + 2 * INTERVAL, 100.0, 111.0, 94.0, 100.0),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].entry_time == T0 + INTERVAL
    assert result.trades[0].exit_time == T0 + 2 * INTERVAL


def test_run_gap_through_at_open_fills_at_open_not_stale_level() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + 2 * INTERVAL, 90.0, 91.0, 89.0, 90.5),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(90.0 * (1 - config.slippage_pct))


def test_run_rejects_signal_with_stop_invalid_relative_to_entry_fill() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 101.0, 99.0, 100.5),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=105.0, take_profit_price=110.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert not result.trades
    assert len(result.rejected_signals) == 1
    assert result.rejected_signals[0].reason == "invalid_stop_placement"


def test_run_does_not_reenter_on_the_same_candle_as_an_exit() -> None:
    # sig-1 opens at index1 (entry candle has no touch, position carries
    # over). sig-2 is timestamped at index1's close, so it targets entry at
    # index2 -- the SAME candle where sig-1's position gets stopped out.
    # Because index2 is spent managing sig-1's exit, sig-2 must be skipped
    # entirely (not even deferred to index3): only 1 trade should result.
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + 2 * INTERVAL, 100.0, 111.0, 94.0, 100.0),
        _row(T0 + 3 * INTERVAL, 100.0, 100.5, 99.5, 100.0),
    ]
    signals = [
        Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0),
        Signal(signal_id="sig-2", timestamp=T0 + INTERVAL, direction="long", stop_loss_price=98.0, take_profit_price=112.0),
    ]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_time == T0 + 2 * INTERVAL
    assert not result.rejected_signals


def test_run_force_closes_open_position_at_end_of_data() -> None:
    config = _config()
    rows = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 102.0, 99.0, 101.0),
        _row(T0 + 2 * INTERVAL, 101.0, 103.0, 100.5, 102.0),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end_of_data"
    assert result.trades[0].exit_time == T0 + 2 * INTERVAL


def test_run_raises_on_incomplete_dataset_by_default() -> None:
    config = _config()
    rows = [_row(T0, 100.0, 100.5, 99.5, 100.0)]

    with pytest.raises(DataIntegrityError):
        run(_ohlcv(rows), [], _quality(status="incomplete"), config)


def test_run_allows_incomplete_dataset_when_flag_set() -> None:
    config = _config(allow_incomplete_dataset=True)
    rows = [_row(T0, 100.0, 100.5, 99.5, 100.0)]

    result = run(_ohlcv(rows), [], _quality(status="incomplete"), config)

    assert result.dataset_quality.status == "incomplete"


def test_run_look_ahead_regression_future_mutation_does_not_change_past_results() -> None:
    config = _config()
    rows_a = [
        _row(T0, 100.0, 100.5, 99.5, 100.0),
        _row(T0 + INTERVAL, 100.0, 111.0, 99.0, 105.0),
        _row(T0 + 2 * INTERVAL, 105.0, 106.0, 104.0, 105.5),
        _row(T0 + 3 * INTERVAL, 105.5, 106.5, 105.0, 106.0),
    ]
    rows_b = rows_a[:3] + [_row(T0 + 3 * INTERVAL, 999.0, 999.0, 1.0, 500.0)]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=110.0)]

    result_a = run(_ohlcv(rows_a), signals, _quality(), config)
    result_b = run(_ohlcv(rows_b), signals, _quality(), config)

    assert result_a.trades[0] == result_b.trades[0]
    curve_a = result_a.equity_curve.head(3).to_dicts()
    curve_b = result_b.equity_curve.head(3).to_dicts()
    assert curve_a == curve_b


def test_run_end_to_end_hand_computed_small_series() -> None:
    config = _config(initial_capital=10000.0, leverage=1.0, risk_per_trade_pct=0.01, fee_pct=0.0, slippage_pct=0.0)
    rows = [
        _row(T0, 100.0, 100.0, 100.0, 100.0),
        _row(T0 + INTERVAL, 100.0, 108.0, 99.0, 107.0),
        _row(T0 + 2 * INTERVAL, 107.0, 107.5, 106.5, 107.0),
    ]
    signals = [Signal(signal_id="sig-1", timestamp=T0, direction="long", stop_loss_price=95.0, take_profit_price=108.0)]

    result = run(_ohlcv(rows), signals, _quality(), config)

    expected_quantity = (10000.0 * 0.01) / (100.0 - 95.0)
    expected_pnl = (108.0 - 100.0) * expected_quantity

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.quantity == pytest.approx(expected_quantity)
    assert trade.exit_price == pytest.approx(108.0)
    assert trade.pnl == pytest.approx(expected_pnl)
    assert result.metrics.total_trades == 1
    assert result.metrics.win_rate == pytest.approx(1.0)
    assert result.config is config
    assert result.dataset_quality.status == "complete"

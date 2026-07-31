from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from strategy.ema_trend_pullback import generate_signals
from strategy.indicators import atr, ema

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _uptrend_with_dip(count: int, dip_index: int, dip_amount: float) -> pl.DataFrame:
    """A steady linear uptrend (close = 100 + 0.1*i) with a single-candle
    dip inserted at dip_index, then a normal-trend candle right after it.
    The dip pulls that candle's close below EMA20; the very next candle's
    close (back on the undipped trend line) recovers above EMA20, while
    the long-running uptrend keeps EMA50 > EMA200 throughout."""
    rows = []
    for i in range(count):
        close = 100.0 + 0.1 * i
        if i == dip_index:
            close -= dip_amount
        rows.append(
            {
                "timestamp": START + i * INTERVAL,
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1.0,
            }
        )
    return pl.DataFrame(rows)


def _downtrend_with_spike(count: int, spike_index: int, spike_amount: float) -> pl.DataFrame:
    rows = []
    for i in range(count):
        close = 200.0 - 0.1 * i
        if i == spike_index:
            close += spike_amount
        rows.append(
            {
                "timestamp": START + i * INTERVAL,
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1.0,
            }
        )
    return pl.DataFrame(rows)


def test_generate_signals_emits_nothing_before_warmup() -> None:
    df = _uptrend_with_dip(199, dip_index=150, dip_amount=3.0)

    signals = generate_signals(df)

    assert signals == []


def test_generate_signals_long_signal_matches_hand_computed_levels() -> None:
    df = _uptrend_with_dip(250, dip_index=220, dip_amount=3.0)

    signals = generate_signals(df)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.direction == "long"

    ema20 = ema(df, "close", 20).to_list()
    atr14 = atr(df, 14).to_list()
    timestamps = df["timestamp"].to_list()
    idx = timestamps.index(signal.timestamp)
    close = df["close"].to_list()[idx]

    assert close > ema20[idx]
    assert df["close"].to_list()[idx - 1] < ema20[idx - 1]

    risk_distance = atr14[idx] * 1.5
    assert signal.stop_loss_price == pytest.approx(close - risk_distance)
    assert signal.take_profit_price == pytest.approx(close + 2 * risk_distance)
    assert signal.signal_id == signal.timestamp.isoformat()


def test_generate_signals_short_signal_matches_hand_computed_levels() -> None:
    df = _downtrend_with_spike(250, spike_index=220, spike_amount=3.0)

    signals = generate_signals(df)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.direction == "short"

    ema20 = ema(df, "close", 20).to_list()
    atr14 = atr(df, 14).to_list()
    timestamps = df["timestamp"].to_list()
    idx = timestamps.index(signal.timestamp)
    close = df["close"].to_list()[idx]

    assert close < ema20[idx]
    assert df["close"].to_list()[idx - 1] > ema20[idx - 1]

    risk_distance = atr14[idx] * 1.5
    assert signal.stop_loss_price == pytest.approx(close + risk_distance)
    assert signal.take_profit_price == pytest.approx(close - 2 * risk_distance)


def test_generate_signals_no_signal_without_pullback() -> None:
    df = _uptrend_with_dip(250, dip_index=220, dip_amount=0.0)

    signals = generate_signals(df)

    assert signals == []


def test_generate_signals_signal_timestamp_is_the_signal_candle() -> None:
    df = _uptrend_with_dip(250, dip_index=220, dip_amount=3.0)

    signals = generate_signals(df)

    timestamps = df["timestamp"].to_list()
    idx = timestamps.index(signals[0].timestamp)

    assert signals[0].timestamp != timestamps[idx - 1]
    assert idx + 1 >= len(timestamps) or signals[0].timestamp != timestamps[idx + 1]


def test_generate_signals_look_ahead_regression() -> None:
    df_a = _uptrend_with_dip(250, dip_index=220, dip_amount=3.0)
    signals_a = generate_signals(df_a)
    assert len(signals_a) == 1

    rows = df_a.to_dicts()
    timestamps = df_a["timestamp"].to_list()
    signal_index = timestamps.index(signals_a[0].timestamp)

    mutated_rows = rows[: signal_index + 1] + [
        {**r, "close": 999.0, "open": 999.0, "high": 999.0, "low": 1.0}
        for r in rows[signal_index + 1 :]
    ]
    df_b = pl.DataFrame(mutated_rows)

    signals_b = generate_signals(df_b)

    assert signals_b[0] == signals_a[0]

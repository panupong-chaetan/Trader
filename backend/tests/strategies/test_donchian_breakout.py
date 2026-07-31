from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from strategies.donchian_breakout import (
    ATR_PERIOD,
    ATR_STOP_MULTIPLIER,
    CHANNEL_PERIOD,
    REWARD_RISK_RATIO,
    generate_signals,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _row(ts, o, h, l, c) -> dict:
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


def _flat_rows(count: int, price: float = 100.0, half_range: float = 0.5) -> list[dict]:
    return [
        _row(START + i * INTERVAL, price, price + half_range, price - half_range, price)
        for i in range(count)
    ]


def _expected_atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float | None]:
    n = len(highs)
    true_ranges: list[float | None] = [None] * n
    for i in range(1, n):
        true_ranges[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    result: list[float | None] = [None] * n
    if n <= period:
        return result
    result[period] = sum(true_ranges[1 : period + 1]) / period
    for i in range(period + 1, n):
        result[i] = (result[i - 1] * (period - 1) + true_ranges[i]) / period
    return result


def test_generate_signals_emits_nothing_before_warmup() -> None:
    # Exactly CHANNEL_PERIOD rows: index CHANNEL_PERIOD (the earliest
    # possible signal index) does not exist yet.
    rows = _flat_rows(CHANNEL_PERIOD)
    rows[-1] = _row(rows[-1]["timestamp"], 100.0, 500.0, 100.0, 300.0)  # would-be breakout
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    assert signals == []


def test_generate_signals_long_signal_matches_hand_computed_levels() -> None:
    rows = _flat_rows(25)
    # Breakout candle: close well above the flat 100.5 channel high, and
    # the candle's own high is deliberately far above its own close --
    # see test_generate_signals_current_candle_excluded_from_channel for
    # why this also matters.
    rows.append(_row(START + 25 * INTERVAL, 100.0, 106.0, 99.5, 105.0))
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.direction == "long"
    assert signal.timestamp == rows[25]["timestamp"]

    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    closes = [r["close"] for r in rows]
    atr = _expected_atr(highs, lows, closes, ATR_PERIOD)
    risk_distance = atr[25] * ATR_STOP_MULTIPLIER

    assert signal.stop_loss_price == pytest.approx(closes[25] - risk_distance)
    assert signal.take_profit_price == pytest.approx(closes[25] + REWARD_RISK_RATIO * risk_distance)
    assert signal.signal_id == signal.timestamp.isoformat()


def test_generate_signals_short_signal_matches_hand_computed_levels() -> None:
    rows = _flat_rows(25)
    rows.append(_row(START + 25 * INTERVAL, 100.0, 100.5, 94.0, 95.0))
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.direction == "short"

    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    closes = [r["close"] for r in rows]
    atr = _expected_atr(highs, lows, closes, ATR_PERIOD)
    risk_distance = atr[25] * ATR_STOP_MULTIPLIER

    assert signal.stop_loss_price == pytest.approx(closes[25] + risk_distance)
    assert signal.take_profit_price == pytest.approx(closes[25] - REWARD_RISK_RATIO * risk_distance)


def test_generate_signals_no_signal_without_breakout() -> None:
    rows = _flat_rows(30)
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    assert signals == []


def test_generate_signals_current_candle_excluded_from_channel() -> None:
    # The signal candle's own high (200) is far above its own close (105).
    # If the implementation wrongly included the current candle in the
    # channel calculation, channel_high would become >= 200, and
    # close(105) could never exceed it -- no signal would ever fire for
    # ANY candle. Asserting a signal DOES fire here is a direct,
    # discriminating proof that the current candle is excluded.
    rows = _flat_rows(25)
    rows.append(_row(START + 25 * INTERVAL, 100.0, 200.0, 99.5, 105.0))
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    assert len(signals) == 1
    assert signals[0].direction == "long"


def test_generate_signals_channel_reflects_prior_20_candles_only() -> None:
    # Window for signal index 25 is candles [5, 25). Mutating index 4
    # (just before the window) to an extreme high must NOT suppress a
    # breakout at close=105 -- if the window were off-by-one too wide
    # (e.g. [4, 25)), that extreme value would raise the channel high to
    # ~999 and block the signal. Asserting the signal still fires proves
    # the window starts at exactly index 5, not index 4.
    rows = _flat_rows(25)
    rows[4] = _row(rows[4]["timestamp"], 100.0, 999.0, 100.0, 100.0)
    rows.append(_row(START + 25 * INTERVAL, 100.0, 106.0, 99.5, 105.0))

    signals = generate_signals(pl.DataFrame(rows))

    assert len(signals) == 1
    assert signals[0].direction == "long"

    # Candles genuinely inside the window [5, 25) must matter: a close
    # that does NOT clear the baseline channel high can become a
    # breakout once every candle inside the window is lowered.
    baseline_rows = _flat_rows(25)
    baseline_rows.append(_row(START + 25 * INTERVAL, 100.0, 100.5, 99.5, 100.4))
    assert generate_signals(pl.DataFrame(baseline_rows)) == []

    lowered_rows = [dict(r) for r in baseline_rows]
    for i in range(5, 25):
        lowered_rows[i] = _row(lowered_rows[i]["timestamp"], 99.0, 99.3, 98.7, 99.0)
    lowered_signals = generate_signals(pl.DataFrame(lowered_rows))

    assert len(lowered_signals) == 1
    assert lowered_signals[0].direction == "long"


def test_generate_signals_signal_timestamp_is_the_signal_candle() -> None:
    rows = _flat_rows(25)
    rows.append(_row(START + 25 * INTERVAL, 100.0, 106.0, 99.5, 105.0))
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    timestamps = [r["timestamp"] for r in rows]
    idx = timestamps.index(signals[0].timestamp)
    assert signals[0].timestamp != timestamps[idx - 1]
    assert idx + 1 >= len(timestamps) or signals[0].timestamp != timestamps[idx + 1]


def test_generate_signals_look_ahead_regression() -> None:
    rows = _flat_rows(25)
    rows.append(_row(START + 25 * INTERVAL, 100.0, 106.0, 99.5, 105.0))
    for i in range(26, 31):
        rows.append(_row(START + i * INTERVAL, 105.0, 105.5, 104.5, 105.0))

    signals_a = generate_signals(pl.DataFrame(rows))
    assert len(signals_a) == 1

    mutated_rows = [dict(r) for r in rows]
    for i in range(26, 31):
        mutated_rows[i] = _row(mutated_rows[i]["timestamp"], 999.0, 999.0, 1.0, 500.0)
    signals_b = generate_signals(pl.DataFrame(mutated_rows))

    assert signals_b[0] == signals_a[0]

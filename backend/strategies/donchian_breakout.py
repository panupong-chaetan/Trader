from __future__ import annotations

import polars as pl

from engine.models import Signal

CHANNEL_PERIOD = 20
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 2.0
REWARD_RISK_RATIO = 2.0


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float | None]:
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

    seed_values = true_ranges[1 : period + 1]
    result[period] = sum(seed_values) / period
    for i in range(period + 1, n):
        result[i] = (result[i - 1] * (period - 1) + true_ranges[i]) / period

    return result


def generate_signals(ohlcv: pl.DataFrame) -> list[Signal]:
    highs = ohlcv["high"].to_list()
    lows = ohlcv["low"].to_list()
    closes = ohlcv["close"].to_list()
    timestamps = ohlcv["timestamp"].to_list()
    n = len(ohlcv)

    atr14 = _atr(highs, lows, closes, ATR_PERIOD)

    signals: list[Signal] = []
    for i in range(CHANNEL_PERIOD, n):
        if atr14[i] is None:
            continue

        channel_high = max(highs[i - CHANNEL_PERIOD : i])
        channel_low = min(lows[i - CHANNEL_PERIOD : i])

        risk_distance = atr14[i] * ATR_STOP_MULTIPLIER

        is_long = closes[i] > channel_high
        is_short = closes[i] < channel_low

        if is_long:
            signals.append(
                Signal(
                    signal_id=timestamps[i].isoformat(),
                    timestamp=timestamps[i],
                    direction="long",
                    stop_loss_price=closes[i] - risk_distance,
                    take_profit_price=closes[i] + REWARD_RISK_RATIO * risk_distance,
                )
            )
        elif is_short:
            signals.append(
                Signal(
                    signal_id=timestamps[i].isoformat(),
                    timestamp=timestamps[i],
                    direction="short",
                    stop_loss_price=closes[i] + risk_distance,
                    take_profit_price=closes[i] - REWARD_RISK_RATIO * risk_distance,
                )
            )

    return signals

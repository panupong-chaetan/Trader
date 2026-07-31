from __future__ import annotations

import polars as pl

from engine.models import Signal
from strategy.indicators import atr, ema

EMA_FAST = 20
EMA_MEDIUM = 50
EMA_SLOW = 200
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5
REWARD_RISK_RATIO = 2.0


def generate_signals(ohlcv: pl.DataFrame) -> list[Signal]:
    ema20 = ema(ohlcv, "close", EMA_FAST).to_list()
    ema50 = ema(ohlcv, "close", EMA_MEDIUM).to_list()
    ema200 = ema(ohlcv, "close", EMA_SLOW).to_list()
    atr14 = atr(ohlcv, ATR_PERIOD).to_list()
    closes = ohlcv["close"].to_list()
    timestamps = ohlcv["timestamp"].to_list()

    signals: list[Signal] = []
    for i in range(EMA_SLOW, len(ohlcv)):
        if ema200[i] is None or ema200[i - 1] is None or atr14[i] is None:
            continue

        risk_distance = atr14[i] * ATR_STOP_MULTIPLIER

        is_long = (
            ema50[i] > ema200[i]
            and closes[i - 1] < ema20[i - 1]
            and closes[i] > ema20[i]
        )
        is_short = (
            ema50[i] < ema200[i]
            and closes[i - 1] > ema20[i - 1]
            and closes[i] < ema20[i]
        )

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

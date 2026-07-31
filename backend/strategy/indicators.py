from __future__ import annotations

import polars as pl


def ema(df: pl.DataFrame, column: str, period: int) -> pl.Series:
    values = df[column].to_list()
    n = len(values)
    result: list[float | None] = [None] * n

    if n < period:
        return pl.Series(column, result)

    alpha = 2 / (period + 1)
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        result[i] = values[i] * alpha + result[i - 1] * (1 - alpha)

    return pl.Series(column, result)


def atr(df: pl.DataFrame, period: int) -> pl.Series:
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
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
        return pl.Series("atr", result)

    seed_values = true_ranges[1 : period + 1]
    result[period] = sum(seed_values) / period
    for i in range(period + 1, n):
        result[i] = (result[i - 1] * (period - 1) + true_ranges[i]) / period

    return pl.Series("atr", result)

# Sample Strategy — EMA Trend Pullback — Milestone Design

Date: 2026-07-31
Project: Trader v2 — Phase 1
Milestone: Sample Strategy (EMA Trend Pullback, 15m)

## Overview

Implement the EMA Trend Pullback strategy exactly as specified in the
project's Sample Strategy section. This strategy exists solely to validate
the Backtesting Engine milestone with real, non-trivial signals — it is
**not** a claim of profitability. It generates `engine.models.Signal`
objects only; it never touches sizing, fees, slippage, or execution — all
of that already lives in `risk`/`engine`, per the project's module
separation rule.

## Goals

- Compute EMA(20), EMA(50), EMA(200), and ATR(14) from OHLCV data using
  fixed, non-optimizable formulas.
- Detect the exact long/short pullback conditions specified by the project,
  candle-by-candle, using only current and past data.
- Emit one `Signal` per qualifying candle with stop-loss/take-profit prices
  computed from the signal candle's close.
- Respect a warm-up period so no signal is emitted before indicators are
  numerically valid.

## Non-Goals

- Position sizing, fee/slippage application, order execution — the engine
  and risk modules already own this.
- Parameter optimization of any kind (periods, ATR multiplier, R-multiple
  are fixed exactly as specified).
- Any strategy other than EMA Trend Pullback.
- Multi-symbol/multi-timeframe support.

## Architecture

```
Trader_v2/
  backend/
    strategy/
      __init__.py
      indicators.py            # ema(), atr() — generic, reusable, no strategy logic
      ema_trend_pullback.py       # generate_signals() — the only file that knows the rules
    tests/
      strategy/
        test_indicators.py
        test_ema_trend_pullback.py
```

`indicators.py` has no dependency on `ema_trend_pullback.py` or
`engine.models` — it is pure `pl.DataFrame -> pl.Series` math, independently
testable and reusable by any future strategy.

## Indicators (`strategy/indicators.py`)

### EMA

```python
def ema(df: pl.DataFrame, column: str, period: int) -> pl.Series
```

- Values at index `< period - 1`: `null` (not enough data yet).
- Value at index `period - 1` (the seed): the **simple moving average** of
  the first `period` values of `column`.
- Values at index `>= period`: `value[i] = price[i] * alpha + value[i-1] * (1 - alpha)`,
  where `alpha = 2 / (period + 1)`.

This is a deliberate departure from `polars`' built-in `ewm_mean(adjust=False)`
(which seeds with the very first raw value) — SMA-seeding is the more
common convention in charting platforms and avoids a large initial-value
bias in the first `period` bars, so it's implemented explicitly rather than
via the built-in.

### ATR

```python
def atr(df: pl.DataFrame, period: int) -> pl.Series
```

- True Range at index `i` (for `i >= 1`): `max(high[i]-low[i], |high[i]-close[i-1]|, |low[i]-close[i-1]|)`.
  Index `0` has no prior close, so True Range and ATR are `null` there.
- Values at index `< period` (i.e. before `period` True Range values exist):
  `null`.
- Value at index `period` (the seed): the simple moving average of True
  Range values at indices `1..period` (Wilder's original seeding — the
  first `period` True Range values, which start at index 1 since index 0
  has none).
- Values at index `> period`: Wilder's RMA recursion:
  `atr[i] = (atr[i-1] * (period - 1) + true_range[i]) / period`.

## Signal Generation (`strategy/ema_trend_pullback.py`)

```python
def generate_signals(ohlcv: pl.DataFrame) -> list[Signal]
```

Fixed parameters (never configurable — no optimization in Phase 1):
`EMA_FAST = 20`, `EMA_MEDIUM = 50`, `EMA_SLOW = 200`, `ATR_PERIOD = 14`,
`ATR_STOP_MULTIPLIER = 1.5`, `REWARD_RISK_RATIO = 2.0`.

1. Compute `ema20`, `ema50`, `ema200` (via `indicators.ema`) and `atr14`
   (via `indicators.atr`) once over the full input.
2. **Warm-up**: the earliest index at which a signal can be evaluated is
   `EMA_SLOW` (`200`, zero-indexed) — this is the first index `i` where
   both `ema200[i]` (valid from index `199` onward) and `ema200[i-1]`
   (valid from index `199`, so needs `i-1 >= 199` i.e. `i >= 200`) are
   non-null. Indices before `200` never emit a signal, regardless of price
   pattern.
3. For each index `i` from `200` to the last row:
   - **Long**: `ema50[i] > ema200[i]` and `close[i-1] < ema20[i-1]` and
     `close[i] > ema20[i]`.
     - `risk_distance = atr14[i] * 1.5`
     - `stop_loss_price = close[i] - risk_distance`
     - `take_profit_price = close[i] + 2 * risk_distance`
   - **Short**: `ema50[i] < ema200[i]` and `close[i-1] > ema20[i-1]` and
     `close[i] < ema20[i]`.
     - `risk_distance = atr14[i] * 1.5`
     - `stop_loss_price = close[i] + risk_distance`
     - `take_profit_price = close[i] - 2 * risk_distance`
   - Long and short conditions are mutually exclusive (the trend filter
     `ema50 vs ema200` can only point one direction at a time) — no
     tie-break is needed.
   - If neither condition holds, no signal is emitted for that index.
4. Each emitted signal: `Signal(signal_id=timestamp[i].isoformat(), timestamp=timestamp[i], direction=..., stop_loss_price=..., take_profit_price=...)`.

Signal timing matches the project spec and the already-implemented engine
exactly: the signal's `timestamp` is the **signal candle's own close**
time; the engine (already built) is solely responsible for entering at the
**next** candle's open. This strategy module never decides entry timing —
it only reports when the pattern completed.

## Look-Ahead Bias Prevention

- Both `ema` and `atr` are strictly causal: each value is a function of
  the current and only prior values (recursive formulas), never of any
  future row.
- The signal condition at index `i` reads only `ema20/ema50/ema200/atr14`
  and `close` at indices `i` and `i-1` — never `i+1` or later.
- **Regression test**: generate signals on a series, then generate again
  on the same series with every candle *after* a known signal mutated to
  extreme values; assert the signal list is identical up to and including
  that signal.

## Testing Strategy

- `test_indicators.py`:
  - `ema`: hand-computed on a small (6-8 point) synthetic close series —
    nulls before the seed index, SMA at the seed index, recursive formula
    after.
  - `atr`: hand-computed on a small synthetic OHLC series with known True
    Range values — null at index 0 and before the seed, SMA seed, Wilder
    RMA recursion after.
- `test_ema_trend_pullback.py`:
  - **Warm-up**: a series shorter than 200 candles, or a qualifying
    crossover pattern placed before index 200, produces zero signals.
  - **Long condition**: constructed series with `ema50 > ema200` and the
    exact prev-below/signal-above EMA20 pullback pattern at a known index
    `>= 200`; assert exactly one long `Signal` with hand-computed
    `stop_loss_price`/`take_profit_price` from the known close and ATR at
    that index.
  - **Short condition**: mirror of the long test.
  - **No false signal**: `ema50 > ema200` holds but there is no
    below-then-above EMA20 pullback — zero signals.
  - **Signal timing**: the emitted `Signal.timestamp` equals the signal
    candle's own timestamp (not the previous or next candle).
  - **Look-ahead regression test** as described above.

## Known Limitations

- EMA seeding (SMA of first `period` values) and ATR seeding (Wilder's
  original SMA-of-True-Range) are two different, deliberately chosen
  conventions — consistent with how each indicator is most commonly
  defined, not a uniform "one seeding method for everything" choice.
- No signal can be evaluated in the first 200 candles of any dataset,
  regardless of how much history is actually needed for the specific EMA
  periods in play at that moment (e.g. EMA20 is numerically valid much
  earlier) — this is a deliberate simplification tied to the slowest
  indicator (EMA200) rather than a per-indicator warm-up.

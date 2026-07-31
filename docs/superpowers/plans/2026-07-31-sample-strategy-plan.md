# Sample Strategy (EMA Trend Pullback) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the EMA Trend Pullback strategy exactly as specified in `docs/superpowers/specs/2026-07-31-sample-strategy-design.md` — a `strategy` module that emits `engine.models.Signal` objects only, with no sizing/fee/slippage/execution logic.

**Architecture:** Two files — `strategy/indicators.py` (generic, reusable EMA/ATR math) and `strategy/ema_trend_pullback.py` (the fixed-parameter crossover/pullback rule that consumes those indicators and returns `list[Signal]`).

**Tech Stack:** Python 3.14, Polars, pytest. No new dependencies.

## Global Constraints

- Every function has type hints; use `logging`, never `print()`.
- `indicators.py` has zero knowledge of the strategy's rules — pure `pl.DataFrame -> pl.Series` math.
- `ema_trend_pullback.py` never imports `pathlib.Path`, `data.storage`, or anything from `risk`/`engine.backtester` — it only imports `engine.models.Signal` for its return type.
- EMA periods, ATR period/multiplier, and reward:risk ratio are hardcoded module-level constants — never configurable, never optimized.
- Do not run `git commit` unless explicitly asked.

All file paths below are relative to `Trader_v2/`.

---

### Task 1: Indicators (`strategy/indicators.py`)

**Files:**
- Create: `backend/strategy/__init__.py`
- Create: `backend/strategy/indicators.py`
- Create: `backend/tests/strategy/__init__.py`
- Test: `backend/tests/strategy/test_indicators.py`

**Interfaces:**
- Produces: `strategy.indicators.ema(df: pl.DataFrame, column: str, period: int) -> pl.Series` and `strategy.indicators.atr(df: pl.DataFrame, period: int) -> pl.Series` (expects `high`, `low`, `close` columns). Consumed directly by Task 2.

- [ ] **Step 1: Scaffold the package**

Create empty `backend/strategy/__init__.py` and `backend/tests/strategy/__init__.py`.
In `backend/pyproject.toml`, change:
```toml
include = ["data*", "risk*", "engine*", "analytics*"]
```
to:
```toml
include = ["data*", "risk*", "engine*", "analytics*", "strategy*"]
```
Run (from `backend/`): `./.venv/Scripts/python.exe -m pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing tests**

`backend/tests/strategy/test_indicators.py`:

```python
import polars as pl
import pytest

from strategy.indicators import atr, ema


def test_ema_matches_documented_formula_end_to_end() -> None:
    df = pl.DataFrame({"close": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]})

    result = ema(df, "close", 3).to_list()

    assert result[0] is None
    assert result[1] is None

    alpha = 2 / (3 + 1)
    closes = df["close"].to_list()
    expected = [sum(closes[:3]) / 3]
    for i in range(3, 6):
        expected.append(closes[i] * alpha + expected[-1] * (1 - alpha))

    assert result[2:] == pytest.approx(expected)


def test_ema_returns_all_null_when_shorter_than_period() -> None:
    df = pl.DataFrame({"close": [10.0, 11.0]})

    result = ema(df, "close", 5).to_list()

    assert result == [None, None]


def test_atr_matches_documented_formula_end_to_end() -> None:
    df = pl.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 13.0, 9.0, 10.0],
            "low": [8.0, 9.0, 10.0, 11.0, 7.0, 8.0],
            "close": [9.0, 10.0, 11.0, 12.0, 8.0, 9.0],
        }
    )

    result = atr(df, 3).to_list()

    assert result[:3] == [None, None, None]

    true_ranges = [None, 2.0, 2.0, 2.0, 5.0, 2.0]
    seed = sum(true_ranges[1:4]) / 3
    expected = [seed]
    for i in range(4, 6):
        expected.append((expected[-1] * (3 - 1) + true_ranges[i]) / 3)

    assert result[3:] == pytest.approx(expected)


def test_atr_index_zero_and_before_seed_are_null() -> None:
    df = pl.DataFrame(
        {
            "high": [10.0, 11.0, 12.0],
            "low": [8.0, 9.0, 10.0],
            "close": [9.0, 10.0, 11.0],
        }
    )

    result = atr(df, 5).to_list()

    assert result == [None, None, None]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/strategy/test_indicators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'strategy.indicators'`

- [ ] **Step 4: Implement the indicators**

`backend/strategy/indicators.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/strategy/test_indicators.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/` and confirm the full suite (90 previous + 4 new) passes.

---

### Task 2: Signal generation (`strategy/ema_trend_pullback.py`)

**Files:**
- Create: `backend/strategy/ema_trend_pullback.py`
- Test: `backend/tests/strategy/test_ema_trend_pullback.py`

**Interfaces:**
- Consumes: `strategy.indicators.ema` / `atr` (Task 1), `engine.models.Signal` (existing).
- Produces: `strategy.ema_trend_pullback.generate_signals(ohlcv: pl.DataFrame) -> list[Signal]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/strategy/test_ema_trend_pullback.py`:

```python
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


def test_generate_signals_emits_nothing_before_warmup() -> None:
    df = _uptrend_with_dip(199, dip_index=150, dip_amount=3.0)

    signals = generate_signals(df)

    assert signals == []


def test_generate_signals_long_signal_matches_hand_computed_levels() -> None:
    df = _uptrend_with_dip(250, dip_index=220, dip_amount=3.0)

    signals = generate_signals(df)

    assert len(signals) >= 1
    signal = signals[0]
    assert signal.direction == "long"

    ema20 = ema(df, "close", 20).to_list()
    atr14 = atr(df, 14).to_list()
    idx = df["timestamp"].to_list().index(signal.timestamp)
    close = df["close"].to_list()[idx]

    assert close > ema20[idx]
    assert df["close"].to_list()[idx - 1] < ema20[idx - 1]

    risk_distance = atr14[idx] * 1.5
    assert signal.stop_loss_price == pytest.approx(close - risk_distance)
    assert signal.take_profit_price == pytest.approx(close + 2 * risk_distance)
    assert signal.signal_id == signal.timestamp.isoformat()


def test_generate_signals_short_signal_matches_hand_computed_levels() -> None:
    rows = []
    count, dip_index, dip_amount = 250, 220, 3.0
    for i in range(count):
        close = 200.0 - 0.1 * i
        if i == dip_index:
            close += dip_amount
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
    df = pl.DataFrame(rows)

    signals = generate_signals(df)

    assert len(signals) >= 1
    signal = signals[0]
    assert signal.direction == "short"

    ema20 = ema(df, "close", 20).to_list()
    atr14 = atr(df, 14).to_list()
    idx = df["timestamp"].to_list().index(signal.timestamp)
    close = df["close"].to_list()[idx]

    risk_distance = atr14[idx] * 1.5
    assert signal.stop_loss_price == pytest.approx(close + risk_distance)
    assert signal.take_profit_price == pytest.approx(close - 2 * risk_distance)


def test_generate_signals_no_signal_without_pullback() -> None:
    df = _uptrend_with_dip(250, dip_index=220, dip_amount=0.0)

    signals = generate_signals(df)

    assert signals == []


def test_generate_signals_look_ahead_regression() -> None:
    df_a = _uptrend_with_dip(250, dip_index=220, dip_amount=3.0)
    rows = df_a.to_dicts()
    first_signal_index = rows.index(
        next(r for r in rows if r["timestamp"] == generate_signals(df_a)[0].timestamp)
    )
    mutated_rows = rows[: first_signal_index + 1] + [
        {**r, "close": 999.0, "open": 999.0, "high": 999.0, "low": 1.0}
        for r in rows[first_signal_index + 1 :]
    ]
    df_b = pl.DataFrame(mutated_rows)

    signals_a = generate_signals(df_a)
    signals_b = generate_signals(df_b)

    assert signals_a[0] == signals_b[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/strategy/test_ema_trend_pullback.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'strategy.ema_trend_pullback'`

- [ ] **Step 3: Implement signal generation**

`backend/strategy/ema_trend_pullback.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/strategy/test_ema_trend_pullback.py -v`
Expected: PASS (6 passed). If the `_uptrend_with_dip` construction with
`dip_amount=3.0` does not actually cross EMA20 as intended at index 220 (the
test may need a larger/smaller `dip_amount` or `dip_index` depending on the
exact EMA20 smoothing at that point in a 250-candle series) — this is
expected to require one or two iterations of adjusting the constant in the
test helper based on actual computed values; it is not a sign of a bug in
`generate_signals`. Verify by printing `ema20[dip_index]` and
`closes[dip_index]` / `closes[dip_index + 1]` if a test fails to see
whether the pullback pattern was actually produced.

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/` and confirm the full suite passes.

---

### Task 3: Module README

**Files:**
- Create: `backend/strategy/README.md`

- [ ] **Step 1: Write the README**

```markdown
# strategy — EMA Trend Pullback (Sample Strategy)

Exists solely to validate the Backtesting Engine with real, non-trivial
signals. **Not** a claim of profitability — every strategy is a hypothesis
until tested (see project Development Rules).

## Modules

- `indicators.py` — generic `ema()` (SMA-seeded, then standard EMA
  recursion) and `atr()` (Wilder's SMA-seeded RMA). No strategy knowledge.
- `ema_trend_pullback.py` — `generate_signals(ohlcv) -> list[Signal]`.
  Fixed parameters only (EMA 20/50/200, ATR 14 x1.5 stop, 2R target) — no
  optimization, no configurability, per Phase 1 rules.

## Rules implemented

- Long: EMA50 > EMA200, previous candle closed below EMA20, signal candle
  closes back above EMA20.
- Short: mirror image.
- Stop loss = signal candle close -+ ATR(14) x 1.5; take profit = 2R.
- No signal before candle index 200 (EMA200's warm-up).
- This module **only** returns `Signal` objects — sizing, fees, slippage,
  and execution are entirely the Backtesting Engine's responsibility.

Full rationale: `docs/superpowers/specs/2026-07-31-sample-strategy-design.md`.
```

- [ ] **Step 2: Checkpoint**

Confirm the README renders correctly. No test changes in this task.

---

## Final Verification

- [ ] Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/`
  one more time and confirm the entire suite (Data Pipeline + Backtesting
  Engine + this milestone) passes.
- [ ] Confirm `strategy/indicators.py` has no knowledge of EMA
  20/50/200/ATR-14x1.5/2R specifically (only `ema_trend_pullback.py`
  should reference those fixed numbers).
- [ ] Confirm no `git commit` was run unless explicitly requested.

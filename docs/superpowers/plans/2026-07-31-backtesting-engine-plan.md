# Backtesting Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Trader v2 Backtesting Engine — a sequential bar-by-bar simulator for a single symbol/timeframe that consumes pre-computed signals, sizes positions under a capital/margin/risk model, applies realistic fill/fee/slippage rules, and produces trade history, an equity curve, and performance metrics — exactly as specified in `docs/superpowers/specs/2026-07-31-backtesting-engine-design.md`.

**Architecture:** Three new modules (`risk`, `engine`, `analytics`) plus a filesystem-aware `engine/loader.py` that bridges to the existing `data` (Data Pipeline) module. The simulation core (`engine/backtester.py`) never touches `Path` or the filesystem — it only consumes in-memory `pl.DataFrame`/dataclass inputs, matching the approved design's loader/engine separation.

**Tech Stack:** Python 3.14 (see Data Pipeline's Known Issues — 3.12 is unavailable on this machine), Polars, Pydantic v2, pytest. No FastAPI, CCXT, or Supabase in this milestone.

## Global Constraints

- Every function has type hints; use `logging`, never `print()`.
- One file = one responsibility; `risk`, `engine`, and `analytics` stay separate modules per the project's Development Rules.
- No look-ahead bias: the simulation loop only ever reads the current candle plus already-computed prior state (see spec's "Look-Ahead Bias Prevention").
- `engine/backtester.py` and `risk/sizing.py` and `analytics/metrics.py` must not import `pathlib.Path` or `data.storage` — only `engine/loader.py` may.
- Do not run `git init` (already initialized) — but do **not** run `git commit` either unless the user explicitly asks; end each task with a "Checkpoint" step (re-run tests, confirm green) instead of a commit, consistent with "only commit when requested."
- Same-bar SL/TP conflict: **stop-loss always wins** (conservative tie-break), enforced identically in entry-candle and subsequent-candle processing.
- Gap-through-at-open: if a candle's raw `open` has already passed the stop-loss or take-profit level, the exit fills at that `open` price (adjusted for exit slippage) rather than the stale SL/TP level. This check always uses the candle's raw `open`, uniformly for both the entry candle and later candles — a minor, deliberate simplification of the design doc's slightly different phrasing for the entry-candle case, chosen because it keeps one shared implementation path and the difference (raw open vs. slippage-adjusted fill) is negligible at realistic slippage magnitudes.
- No new entry may be considered on a candle where an existing position's exit was just processed — enforced structurally (each candle's processing is either "manage existing position" or "consider new entry," never both).
- `BacktestConfig` has no `timeframe` field (matches the approved spec exactly). The engine infers the annualization factor for Sharpe directly from the OHLCV timestamps' median interval — see Task 8.

All file paths below are relative to `Trader_v2/`.

---

### Task 1: Package scaffold for `risk`, `engine`, `analytics`

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/risk/__init__.py`
- Create: `backend/engine/__init__.py`
- Create: `backend/analytics/__init__.py`
- Create: `backend/tests/risk/__init__.py`
- Create: `backend/tests/engine/__init__.py`
- Create: `backend/tests/analytics/__init__.py`

- [ ] **Step 1: Update package discovery**

In `backend/pyproject.toml`, change:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["data*"]
```

to:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["data*", "risk*", "engine*", "analytics*"]
```

- [ ] **Step 2: Create empty package files**

Create empty `backend/risk/__init__.py`, `backend/engine/__init__.py`,
`backend/analytics/__init__.py`, `backend/tests/risk/__init__.py`,
`backend/tests/engine/__init__.py`, `backend/tests/analytics/__init__.py`.

- [ ] **Step 3: Reinstall the package**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pip install -e ".[dev]"`
Expected: succeeds, `risk`, `engine`, `analytics` are now importable
(they're empty, so nothing to test yet).

- [ ] **Step 4: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests/data -v` from `backend/` and
confirm the existing 33 Data Pipeline tests still pass (this task only adds
scaffolding, no behavior change).

---

### Task 2: Domain models (`engine/models.py`)

**Files:**
- Create: `backend/engine/models.py`
- Test: `backend/tests/engine/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Signal`, `GapRange`, `DatasetQuality`, `BacktestConfig`,
  `Trade`, `RejectedSignal`, `BacktestMetrics`, `BacktestResult` — all
  dataclasses are `@dataclass(frozen=True)`; `BacktestConfig` is a Pydantic
  `BaseModel`. Every later task in this plan imports from this module.

- [ ] **Step 1: Write the failing test**

`backend/tests/engine/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from engine.models import BacktestConfig


def _base_kwargs() -> dict:
    return {
        "initial_capital": 10000.0,
        "risk_per_trade_pct": 0.01,
        "fee_pct": 0.001,
        "slippage_pct": 0.0005,
    }


def test_backtest_config_accepts_valid_input() -> None:
    config = BacktestConfig(**_base_kwargs())

    assert config.initial_capital == 10000.0
    assert config.leverage == 1.0
    assert config.allow_incomplete_dataset is False


def test_backtest_config_rejects_non_positive_initial_capital() -> None:
    kwargs = _base_kwargs()
    kwargs["initial_capital"] = 0.0

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_non_positive_risk_per_trade_pct() -> None:
    kwargs = _base_kwargs()
    kwargs["risk_per_trade_pct"] = 0.0

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_leverage_below_one() -> None:
    kwargs = _base_kwargs()
    kwargs["leverage"] = 0.5

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_negative_fee_pct() -> None:
    kwargs = _base_kwargs()
    kwargs["fee_pct"] = -0.001

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_negative_slippage_pct() -> None:
    kwargs = _base_kwargs()
    kwargs["slippage_pct"] = -0.0001

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/engine/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.models'`

- [ ] **Step 3: Implement the models**

`backend/engine/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl
from pydantic import BaseModel, field_validator


@dataclass(frozen=True)
class Signal:
    signal_id: str
    timestamp: datetime
    direction: str  # "long" | "short"
    stop_loss_price: float
    take_profit_price: float


@dataclass(frozen=True)
class GapRange:
    start: datetime
    end: datetime
    severity: str


@dataclass(frozen=True)
class DatasetQuality:
    status: str  # "complete" | "incomplete"
    gaps: list[GapRange]


class BacktestConfig(BaseModel):
    initial_capital: float
    leverage: float = 1.0
    risk_per_trade_pct: float
    fee_pct: float
    slippage_pct: float
    allow_incomplete_dataset: bool = False

    @field_validator("initial_capital", "risk_per_trade_pct")
    @classmethod
    def _must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    @field_validator("leverage")
    @classmethod
    def _leverage_at_least_one(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("must be >= 1.0")
        return value

    @field_validator("fee_pct", "slippage_pct")
    @classmethod
    def _must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must be >= 0")
        return value


@dataclass(frozen=True)
class Trade:
    signal_id: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    direction: str  # "long" | "short"
    quantity: float
    stop_loss_price: float
    take_profit_price: float
    exit_reason: str  # "stop_loss" | "take_profit" | "end_of_data"
    entry_fee: float
    exit_fee: float
    equity_before: float
    equity_after: float
    pnl: float
    pnl_pct: float
    r_multiple: float


@dataclass(frozen=True)
class RejectedSignal:
    signal_id: str
    timestamp: datetime
    reason: str  # "invalid_stop_placement" | "zero_stop_distance" | "invalid_quantity" | "insufficient_capital"


@dataclass(frozen=True)
class BacktestMetrics:
    total_trades: int
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    max_consecutive_losses: int | None


@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig
    dataset_quality: DatasetQuality
    trades: list[Trade]
    rejected_signals: list[RejectedSignal]
    equity_curve: pl.DataFrame
    metrics: BacktestMetrics
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_models.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/` and
confirm all tests (Data Pipeline + this task) pass.

---

### Task 3: Position sizing (`risk/sizing.py`)

**Files:**
- Create: `backend/risk/sizing.py`
- Test: `backend/tests/risk/test_sizing.py`

**Interfaces:**
- Consumes: `engine.models.BacktestConfig` (Task 2).
- Produces: `risk.sizing.SizingResult` (`@dataclass(frozen=True)`:
  `accepted: bool`, `quantity: float | None = None`, `reason: str | None = None`)
  and `risk.sizing.size_position(direction: str, entry_price_filled: float, stop_loss_price: float, equity_at_entry: float, config: BacktestConfig) -> SizingResult`.
  Consumed directly by Task 7 (`engine/backtester.py`).

Rejection reasons and the order they're checked, exactly as in the spec but
made independently reachable/testable:
1. `equity_at_entry <= 0` -> `"insufficient_capital"` (checked first).
2. Stop on the wrong side of the entry fill -> `"invalid_stop_placement"`.
3. Stop exactly equal to the entry fill -> `"zero_stop_distance"`.
4. (Defensive, not expected to trigger under validated `BacktestConfig` +
   positive `equity_at_entry`) non-finite or non-positive final quantity ->
   `"invalid_quantity"`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/risk/test_sizing.py`:

```python
import pytest

from engine.models import BacktestConfig
from risk.sizing import size_position


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


def test_size_position_long_valid_matches_documented_formula() -> None:
    config = _config()
    entry, stop, equity = 100.0, 95.0, 10000.0

    stop_exit_price = stop * (1 - config.slippage_pct)
    price_risk = entry - stop_exit_price
    fee_cost = config.fee_pct * (entry + stop_exit_price)
    effective_risk = price_risk + fee_cost
    expected_quantity = (equity * config.risk_per_trade_pct) / effective_risk

    result = size_position("long", entry, stop, equity, config)

    assert result.accepted
    assert result.quantity == pytest.approx(expected_quantity)


def test_size_position_short_valid_matches_documented_formula() -> None:
    config = _config()
    entry, stop, equity = 100.0, 105.0, 10000.0

    stop_exit_price = stop * (1 + config.slippage_pct)
    price_risk = stop_exit_price - entry
    fee_cost = config.fee_pct * (entry + stop_exit_price)
    effective_risk = price_risk + fee_cost
    expected_quantity = (equity * config.risk_per_trade_pct) / effective_risk

    result = size_position("short", entry, stop, equity, config)

    assert result.accepted
    assert result.quantity == pytest.approx(expected_quantity)


def test_size_position_capital_cap_binds_reduces_quantity() -> None:
    config = _config(risk_per_trade_pct=0.5, leverage=1.0)
    entry, stop, equity = 100.0, 99.0, 10000.0

    result = size_position("long", entry, stop, equity, config)

    capital_capped_quantity = (equity * config.leverage) / entry
    assert result.accepted
    assert result.quantity == pytest.approx(capital_capped_quantity)


def test_size_position_rejects_invalid_stop_placement_for_long() -> None:
    config = _config()

    result = size_position("long", 100.0, 105.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "invalid_stop_placement"


def test_size_position_rejects_invalid_stop_placement_for_short() -> None:
    config = _config()

    result = size_position("short", 100.0, 95.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "invalid_stop_placement"


def test_size_position_rejects_zero_stop_distance_for_long() -> None:
    config = _config()

    result = size_position("long", 100.0, 100.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "zero_stop_distance"


def test_size_position_rejects_zero_stop_distance_for_short() -> None:
    config = _config()

    result = size_position("short", 100.0, 100.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "zero_stop_distance"


def test_size_position_rejects_insufficient_capital_when_equity_zero() -> None:
    config = _config()

    result = size_position("long", 100.0, 95.0, 0.0, config)

    assert not result.accepted
    assert result.reason == "insufficient_capital"


def test_size_position_rejects_insufficient_capital_when_equity_negative() -> None:
    config = _config()

    result = size_position("long", 100.0, 95.0, -500.0, config)

    assert not result.accepted
    assert result.reason == "insufficient_capital"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/risk/test_sizing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'risk.sizing'`

- [ ] **Step 3: Implement sizing**

`backend/risk/sizing.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

from engine.models import BacktestConfig


@dataclass(frozen=True)
class SizingResult:
    accepted: bool
    quantity: float | None = None
    reason: str | None = None


def size_position(
    direction: str,
    entry_price_filled: float,
    stop_loss_price: float,
    equity_at_entry: float,
    config: BacktestConfig,
) -> SizingResult:
    if equity_at_entry <= 0:
        return SizingResult(accepted=False, reason="insufficient_capital")

    if direction == "long":
        if stop_loss_price > entry_price_filled:
            return SizingResult(accepted=False, reason="invalid_stop_placement")
        if stop_loss_price == entry_price_filled:
            return SizingResult(accepted=False, reason="zero_stop_distance")
        stop_exit_price = stop_loss_price * (1 - config.slippage_pct)
    else:
        if stop_loss_price < entry_price_filled:
            return SizingResult(accepted=False, reason="invalid_stop_placement")
        if stop_loss_price == entry_price_filled:
            return SizingResult(accepted=False, reason="zero_stop_distance")
        stop_exit_price = stop_loss_price * (1 + config.slippage_pct)

    price_risk_per_unit = abs(entry_price_filled - stop_exit_price)
    fee_cost_per_unit = config.fee_pct * (entry_price_filled + stop_exit_price)
    effective_risk_per_unit = price_risk_per_unit + fee_cost_per_unit

    risk_based_quantity = (equity_at_entry * config.risk_per_trade_pct) / effective_risk_per_unit
    capital_capped_quantity = (equity_at_entry * config.leverage) / entry_price_filled
    quantity = min(risk_based_quantity, capital_capped_quantity)

    if not math.isfinite(quantity) or quantity <= 0:
        return SizingResult(accepted=False, reason="invalid_quantity")

    return SizingResult(accepted=True, quantity=quantity)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/risk/test_sizing.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` and confirm all tests pass.

---

### Task 4: Metrics (`analytics/metrics.py`)

**Files:**
- Create: `backend/analytics/metrics.py`
- Test: `backend/tests/analytics/test_metrics.py`

**Interfaces:**
- Consumes: `engine.models.Trade`, `engine.models.BacktestMetrics` (Task 2).
- Produces: `analytics.metrics.compute_metrics(trades: list[Trade], equity_curve: pl.DataFrame, candles_per_year: int) -> BacktestMetrics`.
  `candles_per_year` is a plain integer annualization factor (no timeframe
  string) — the caller (Task 8's `backtester.run`) derives it directly from
  the OHLCV data. Consumed directly by Task 8.

- [ ] **Step 1: Write the failing tests**

`backend/tests/analytics/test_metrics.py`:

```python
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from analytics.metrics import compute_metrics
from engine.models import Trade

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)


def _trade(pnl: float, index: int) -> Trade:
    t = START + index * INTERVAL
    return Trade(
        signal_id=f"s{index}",
        entry_time=t,
        entry_price=100.0,
        exit_time=t,
        exit_price=100.0,
        direction="long",
        quantity=1.0,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        exit_reason="take_profit" if pnl > 0 else "stop_loss",
        entry_fee=0.0,
        exit_fee=0.0,
        equity_before=1000.0,
        equity_after=1000.0 + pnl,
        pnl=pnl,
        pnl_pct=pnl / 100.0,
        r_multiple=pnl / 10.0,
    )


def _equity_curve(values: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * INTERVAL for i in range(len(values))],
            "equity": values,
        }
    )


def test_compute_metrics_returns_none_for_zero_trades() -> None:
    metrics = compute_metrics([], _equity_curve([1000.0]), 35040)

    assert metrics.total_trades == 0
    assert metrics.win_rate is None
    assert metrics.profit_factor is None
    assert metrics.expectancy is None
    assert metrics.sharpe_ratio is None
    assert metrics.max_drawdown_pct is None
    assert metrics.max_consecutive_losses is None


def test_compute_metrics_win_rate_and_expectancy() -> None:
    trades = [_trade(100.0, 0), _trade(-50.0, 1), _trade(200.0, 2), _trade(-50.0, 3)]
    equity_curve = _equity_curve([1000.0, 1100.0, 1050.0, 1250.0, 1200.0])

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.total_trades == 4
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.expectancy == pytest.approx((100 - 50 + 200 - 50) / 4)


def test_compute_metrics_profit_factor_is_inf_with_no_losses() -> None:
    trades = [_trade(100.0, 0), _trade(50.0, 1)]
    equity_curve = _equity_curve([1000.0, 1100.0, 1150.0])

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.profit_factor == float("inf")


def test_compute_metrics_profit_factor_hand_computed() -> None:
    trades = [_trade(300.0, 0), _trade(-100.0, 1), _trade(-50.0, 2)]
    equity_curve = _equity_curve([1000.0, 1300.0, 1200.0, 1150.0])

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.profit_factor == pytest.approx(300 / 150)


def test_compute_metrics_max_drawdown_hand_computed() -> None:
    equity_curve = _equity_curve([1000.0, 1200.0, 900.0, 950.0, 1300.0, 1100.0])

    metrics = compute_metrics([_trade(100.0, 0)], equity_curve, 35040)

    assert metrics.max_drawdown_pct == pytest.approx(0.25)


def test_compute_metrics_max_consecutive_losses_hand_computed() -> None:
    trades = [
        _trade(10.0, 0), _trade(-5.0, 1), _trade(-5.0, 2),
        _trade(-5.0, 3), _trade(10.0, 4), _trade(-1.0, 5),
    ]
    equity_curve = _equity_curve([1000.0] * 7)

    metrics = compute_metrics(trades, equity_curve, 35040)

    assert metrics.max_consecutive_losses == 3


def test_compute_metrics_sharpe_ratio_zero_when_no_variance() -> None:
    equity_curve = _equity_curve([1000.0, 1000.0, 1000.0, 1000.0])

    metrics = compute_metrics([_trade(0.0, 0)], equity_curve, 35040)

    assert metrics.sharpe_ratio == 0.0


def test_compute_metrics_sharpe_ratio_matches_documented_formula() -> None:
    values = [1000.0, 1010.0, 1005.0, 1030.0, 1020.0]
    equity_curve = _equity_curve(values)

    metrics = compute_metrics([_trade(20.0, 0)], equity_curve, 35040)

    returns = [(values[i] / values[i - 1]) - 1 for i in range(1, len(values))]
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    std_r = variance ** 0.5
    expected_sharpe = (mean_r / std_r) * (35040 ** 0.5)

    assert metrics.sharpe_ratio == pytest.approx(expected_sharpe)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/analytics/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analytics.metrics'`

- [ ] **Step 3: Implement metrics**

`backend/analytics/metrics.py`:

```python
from __future__ import annotations

import math

import polars as pl

from engine.models import BacktestMetrics, Trade


def compute_metrics(
    trades: list[Trade],
    equity_curve: pl.DataFrame,
    candles_per_year: int,
) -> BacktestMetrics:
    total_trades = len(trades)
    if total_trades == 0:
        return BacktestMetrics(
            total_trades=0,
            win_rate=None,
            profit_factor=None,
            expectancy=None,
            sharpe_ratio=None,
            max_drawdown_pct=None,
            max_consecutive_losses=None,
        )

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / total_trades
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = float("inf") if gross_loss == 0 else gross_profit / gross_loss
    expectancy = sum(pnls) / total_trades

    return BacktestMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        sharpe_ratio=_sharpe_ratio(equity_curve, candles_per_year),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        max_consecutive_losses=_max_consecutive_losses(pnls),
    )


def _sharpe_ratio(equity_curve: pl.DataFrame, candles_per_year: int) -> float:
    equity = equity_curve["equity"].to_list()
    if len(equity) < 2:
        return 0.0
    returns = [
        (equity[i] / equity[i - 1]) - 1
        for i in range(1, len(equity))
        if equity[i - 1] != 0
    ]
    if len(returns) < 2:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = math.sqrt(variance)
    if std_return == 0:
        return 0.0
    return (mean_return / std_return) * math.sqrt(candles_per_year)


def _max_drawdown_pct(equity_curve: pl.DataFrame) -> float:
    equity = equity_curve["equity"].to_list()
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def _max_consecutive_losses(pnls: list[float]) -> int:
    longest = 0
    current = 0
    for pnl in pnls:
        if pnl <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/analytics/test_metrics.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` and confirm all tests pass.

---

### Task 5: Loader (`engine/loader.py`)

**Files:**
- Create: `backend/engine/loader.py`
- Test: `backend/tests/engine/test_loader.py`

**Interfaces:**
- Consumes: `data.storage.dataset_paths` / `read_parquet_if_exists` /
  `read_metadata_if_exists` (Data Pipeline module), `engine.models.DatasetQuality`
  / `GapRange` (Task 2).
- Produces: `engine.loader.load_dataset(base_dir: Path, exchange: str, symbol_slug: str, timeframe: str) -> tuple[pl.DataFrame, DatasetQuality]`.
  Raises `FileNotFoundError` if the Parquet or metadata file is missing.
  This is the **only** file in this milestone allowed to import `pathlib.Path`
  or `data.storage`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/engine/test_loader.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from data.config import DownloadConfig
from data.storage import atomic_write, build_metadata, dataset_paths
from engine.loader import load_dataset


def test_load_dataset_returns_dataframe_and_matching_quality(tmp_path: Path) -> None:
    config = DownloadConfig(
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="15m",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame(
        [{"timestamp": t0, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    )
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status="complete")
    atomic_write(df, metadata, paths)

    loaded_df, quality = load_dataset(tmp_path, config.exchange, config.symbol_slug, config.timeframe)

    assert loaded_df.height == 1
    assert quality.status == "complete"
    assert quality.gaps == []


def test_load_dataset_raises_when_parquet_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path, "binance", "BTCUSDT", "15m")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.loader'`

- [ ] **Step 3: Implement the loader**

`backend/engine/loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import polars as pl

from data.storage import dataset_paths, read_metadata_if_exists, read_parquet_if_exists
from engine.models import DatasetQuality, GapRange


def load_dataset(
    base_dir: Path,
    exchange: str,
    symbol_slug: str,
    timeframe: str,
) -> tuple[pl.DataFrame, DatasetQuality]:
    paths = dataset_paths(base_dir, exchange, symbol_slug, timeframe)

    df = read_parquet_if_exists(paths.parquet_path)
    if df is None:
        raise FileNotFoundError(f"No dataset found at {paths.parquet_path}")

    metadata = read_metadata_if_exists(paths.metadata_path)
    if metadata is None:
        raise FileNotFoundError(f"No metadata found at {paths.metadata_path}")

    gaps = [
        GapRange(start=g.start, end=g.end, severity=g.severity)
        for g in metadata.gaps
    ]
    return df, DatasetQuality(status=metadata.status, gaps=gaps)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_loader.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` and confirm all tests pass.

---

### Task 6: Backtester fill/touch/gap helpers (`engine/backtester.py`, part 1)

**Files:**
- Create: `backend/engine/backtester.py`
- Test: `backend/tests/engine/test_backtester.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (private helpers, but documented here since Task 7/8 depend on
  their exact behavior): `_entry_fill_price(direction: str, open_price: float, slippage_pct: float) -> float`,
  `_exit_fill_price(direction: str, raw_price: float, slippage_pct: float) -> float`,
  `TouchResult` (`@dataclass(frozen=True)`: `exit_reason: str | None`,
  `raw_exit_price: float | None`), `_resolve_touch(direction, low, high, stop_loss_price, take_profit_price) -> TouchResult`
  (both-touched -> stop-loss wins), `_resolve_gap_through(direction, open_price, stop_loss_price, take_profit_price) -> TouchResult`.
  Consumed directly by Task 7.

- [ ] **Step 1: Write the failing tests**

`backend/tests/engine/test_backtester.py`:

```python
import pytest

from engine.backtester import _entry_fill_price, _exit_fill_price, _resolve_gap_through, _resolve_touch


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_backtester.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.backtester'`

- [ ] **Step 3: Implement the helpers**

`backend/engine/backtester.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_backtester.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` and confirm all tests pass.

---

### Task 7: Position lifecycle (`engine/backtester.py`, part 2)

**Files:**
- Modify: `backend/engine/backtester.py` (append)
- Modify: `backend/tests/engine/test_backtester.py` (append)

**Interfaces:**
- Consumes: `risk.sizing.size_position` (Task 3), `engine.models.Signal`
  / `Trade` / `RejectedSignal` / `BacktestConfig` (Task 2), `_entry_fill_price`
  / `_exit_fill_price` (Task 6, this file).
- Produces (appended to `engine.backtester`): `_OpenPosition` (internal
  dataclass, not frozen — see below), `_unrealized_gross_pnl(position, mark_price) -> float`,
  `_try_open_position(signal: Signal, row: dict, equity_at_entry: float, config: BacktestConfig) -> tuple[_OpenPosition | None, RejectedSignal | None]`,
  `_close_position(position: _OpenPosition, exit_time: datetime, raw_exit_price: float, exit_reason: str, config: BacktestConfig) -> Trade`.
  Consumed directly by Task 8 (the full `run()` loop).

- [ ] **Step 1: Write the failing tests (append to the existing file)**

Append to `backend/tests/engine/test_backtester.py`:

```python
from datetime import datetime, timezone

from engine.backtester import _close_position, _try_open_position, _unrealized_gross_pnl, _OpenPosition
from engine.models import BacktestConfig, Signal

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


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
    from risk.sizing import size_position

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
```

Add `from engine.backtester import _entry_fill_price` (already imported at
the top of the file from Task 6) and `import pytest` (already present) —
no new top-of-file imports are needed beyond what Task 6 already added,
except the new names imported in the snippet above.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_backtester.py -v`
Expected: FAIL with `ImportError: cannot import name '_try_open_position' from 'engine.backtester'`

- [ ] **Step 3: Implement position lifecycle (append to `backend/engine/backtester.py`)**

```python
from datetime import datetime

from engine.models import BacktestConfig, RejectedSignal, Signal, Trade
from risk.sizing import size_position


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
```

Place `from datetime import datetime` alongside the existing imports at the
top of `backend/engine/backtester.py` (remove the duplicate if one already
exists from Task 6).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_backtester.py -v`
Expected: PASS (20 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` and confirm all tests pass.

---

### Task 8: The `run()` loop (`engine/backtester.py`, part 3)

**Files:**
- Modify: `backend/engine/backtester.py` (append)
- Modify: `backend/tests/engine/test_backtester.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 6–7 in this file, `engine.models.*`
  (Task 2), `data.exceptions.DataIntegrityError` (Data Pipeline module),
  `analytics.metrics.compute_metrics` (Task 4).
- Produces: `engine.backtester.run(ohlcv: pl.DataFrame, signals: list[Signal], dataset_quality: DatasetQuality, config: BacktestConfig) -> BacktestResult`.
  This is the milestone's primary public entry point.

Processing rules implemented here (all traced to the approved spec):
- Raises `DataIntegrityError` if `dataset_quality.status == "incomplete"` and
  `config.allow_incomplete_dataset` is `False`.
- Logs a warning for any gap in `dataset_quality.gaps` that overlaps the
  OHLCV series' date range.
- A signal at row index `i` is only actionable as an entry at row index
  `i + 1` (mapped once via timestamp lookup — if a signal's timestamp isn't
  found in the series, or it's the last row, it's silently unreachable, a
  documented Known Limitation).
- Each candle's processing is mutually exclusive: manage an existing open
  position (gap-through-at-open, then high/low touch), **or** consider a
  new entry (only when the engine started the candle flat) — never both.
  This structurally enforces "no exit and re-entry in the same candle."
- A position still open when the data ends force-closes at the final
  candle's close, `exit_reason = "end_of_data"`.
- The equity curve is mark-to-market every candle.
- The Sharpe annualization factor is inferred from the OHLCV series' own
  median inter-candle interval (no `timeframe` field on `BacktestConfig`).

- [ ] **Step 1: Write the failing tests (append to the existing file)**

Append to `backend/tests/engine/test_backtester.py`:

```python
from datetime import timedelta

import polars as pl

from data.exceptions import DataIntegrityError
from engine.backtester import run
from engine.models import DatasetQuality, GapRange

INTERVAL = timedelta(minutes=15)


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
```

Add `T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)` near the top of the
test file if not already present from Task 7 (reuse the same constant), and
add the new imports shown above alongside the existing ones.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_backtester.py -v`
Expected: FAIL with `ImportError: cannot import name 'run' from 'engine.backtester'`

- [ ] **Step 3: Implement `run()` (append to `backend/engine/backtester.py`)**

```python
import polars as pl

from analytics.metrics import compute_metrics
from data.exceptions import DataIntegrityError
from engine.models import BacktestResult, DatasetQuality


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
```

Consolidate imports at the top of `backend/engine/backtester.py` — by the
end of this task the file's imports should be:

```python
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
```

with all three parts' function/class bodies (Tasks 6, 7, 8) following in
the same file, in the order they were written.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/engine/test_backtester.py -v`
Expected: PASS (32 passed)

- [ ] **Step 5: Checkpoint**

Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/` and
confirm the entire suite (Data Pipeline + this milestone) passes.

---

### Task 9: Module READMEs

**Files:**
- Create: `backend/risk/README.md`
- Create: `backend/engine/README.md`
- Create: `backend/analytics/README.md`

- [ ] **Step 1: Write `backend/risk/README.md`**

```markdown
# risk — Position Sizing

`sizing.py` computes trade quantity from a risk-per-trade percentage, the
actual entry fill price, and the signal's stop-loss price — accounting for
fees and slippage on both legs so that the realized worst-case loss at the
stop is as close as possible to `config.risk_per_trade_pct * equity_at_entry`,
then caps the result by available capital and leverage.

## Rejection reasons

- `invalid_stop_placement` — the stop is on the wrong side of the entry fill.
- `zero_stop_distance` — the stop equals the entry fill exactly.
- `insufficient_capital` — equity at entry is `<= 0`.
- `invalid_quantity` — defensive guard for non-finite/non-positive results;
  not expected to trigger under validated config + positive equity.

See `docs/superpowers/specs/2026-07-31-backtesting-engine-design.md` for
the full formula derivation.
```

- [ ] **Step 2: Write `backend/engine/README.md`**

```markdown
# engine — Backtesting Engine

Sequential, bar-by-bar simulation for a single symbol/timeframe. Consumes
pre-computed `Signal`s (Strategy module territory, not implemented here) and
produces a `BacktestResult` (trades, rejected signals, equity curve,
metrics).

## Modules

- `models.py` — all domain models: `Signal`, `DatasetQuality`,
  `BacktestConfig`, `Trade`, `RejectedSignal`, `BacktestMetrics`,
  `BacktestResult`.
- `loader.py` — the **only** file here that touches the filesystem; reads a
  Parquet + metadata sidecar (via the Data Pipeline's `data.storage`) into
  an in-memory `(pl.DataFrame, DatasetQuality)` pair.
- `backtester.py` — `run(ohlcv, signals, dataset_quality, config)`. Never
  imports `pathlib.Path` — fully unit-testable with synthetic in-memory data.

## Key rules

- Signal at bar `N`'s close -> entry at bar `N+1`'s open.
- Both stop-loss and take-profit touched in one candle -> stop-loss wins.
- A candle's `open` gapping through SL/TP fills at that `open`, not the
  stale level.
- No new entry on the same candle as an exit — enforced structurally, not
  by a flag.
- Incomplete datasets (`DatasetQuality.status == "incomplete"`) raise
  `DataIntegrityError` unless `config.allow_incomplete_dataset=True`.

Full rationale: `docs/superpowers/specs/2026-07-31-backtesting-engine-design.md`.
```

- [ ] **Step 3: Write `backend/analytics/README.md`**

```markdown
# analytics — Performance Metrics

`metrics.py`'s `compute_metrics(trades, equity_curve, candles_per_year)`
returns win rate, profit factor, expectancy, Sharpe ratio, max drawdown,
and max consecutive losses.

- Zero trades -> every metric is `None`.
- No losing trades -> profit factor is `inf`.
- No equity variance -> Sharpe ratio is `0.0`.
- Sharpe uses per-candle equity returns, annualized by `candles_per_year`
  (inferred by the engine from the OHLCV series' own interval — not a
  config field), with a 0% risk-free rate.

See `docs/superpowers/specs/2026-07-31-backtesting-engine-design.md` for
exact formulas.
```

- [ ] **Step 4: Checkpoint**

Confirm the three README files render correctly and cross-check their
content against `sizing.py`, `backtester.py`, and `metrics.py` for
accuracy. No test changes in this task.

---

## Final Verification

- [ ] Run `./.venv/Scripts/python.exe -m pytest tests -v` from `backend/`
  one more time and confirm the entire suite (Data Pipeline's 33 tests +
  this milestone's tests) passes.
- [ ] Confirm `engine/backtester.py`, `risk/sizing.py`, and
  `analytics/metrics.py` contain no `import pathlib` / `from pathlib` and
  no `data.storage` import — only `engine/loader.py` should.
- [ ] Confirm no `git commit` was run during this plan's execution unless
  the user explicitly asked for one.

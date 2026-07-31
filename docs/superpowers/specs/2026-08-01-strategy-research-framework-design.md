# Strategy Research Framework — Milestone Design

Date: 2026-08-01
Project: Trader v2 — Phase 2
Milestone: Strategy Research Framework

## Overview

A minimal, reusable scaffold so that future research strategies (EMA
Cross, Breakout, RSI Mean Reversion, and others) can each be added as a
single new module, all conforming to the same signal-generation contract
already proven by the archived EMA Trend Pullback reference
implementation. This milestone adds no new strategies — it adds the
contract and one automated architectural safeguard.

## Goals

- Define the shared type contract every strategy module must satisfy:
  `generate_signals(ohlcv: pl.DataFrame) -> list[Signal]`.
- Provide one central, automated test that any strategy module dropped
  into the new package does not import execution/sizing/reporting
  concerns — without requiring each strategy to add its own conformance
  test file.
- Document the convention (folder location, one-function-per-module,
  reproducibility rules) so future strategy milestones have a clear,
  consistent pattern to follow.

## Non-Goals

- No implementation of any concrete strategy (EMA Cross, Breakout,
  Donchian, Bollinger, RSI Mean Reversion, MACD, ADX Trend, Supertrend,
  Liquidity Sweep, Fair Value Gap, ICT, Smart Money Concepts, or any
  other) — these are mentioned in the README purely as illustrative
  examples of the kind of module this framework is meant to support, not
  a committed roadmap.
- No registry or auto-discovery mechanism, and no runner/CLI changes.
  Strategies are imported explicitly wherever they're used; this can
  change in a future milestone if/when dynamic strategy selection becomes
  a real requirement.
- No per-strategy runtime conformance helper (e.g. no `assert_conforms`).
  A strategy's behavior and the shape of its returned `Signal` objects are
  verified by that strategy's own normal tests, not by framework
  machinery.
- No shared indicators module is scaffolded speculatively — created later
  by whichever future strategy first needs reusable math (YAGNI).
- No changes whatsoever to `strategy/` (archived), `engine/`, `risk/`,
  `analytics/`, `report/`, `runner/`, `diagnostics/`, or `data/`.

## Architecture

```
Trader_v2/
  backend/
    strategies/
      __init__.py
      contracts.py          # GenerateSignals type alias + assert_no_forbidden_imports
      README.md
    tests/
      strategies/
        __init__.py
        test_architecture.py    # the one central, automatic import-boundary test
```

Adding a future strategy means creating exactly one new file under
`strategies/` plus that strategy's own normal test file (verifying its
specific signal logic, following the precedent set by
`strategy/ema_trend_pullback.py` and `strategy/test_ema_trend_pullback.py`)
— nothing else in the codebase needs to change. `test_architecture.py`
automatically covers the new file for the import-boundary rule with no
further action required.

## The Contract (`strategies/contracts.py`)

```python
from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable

import polars as pl

from engine.models import Signal

GenerateSignals = Callable[[pl.DataFrame], list[Signal]]

FORBIDDEN_IMPORT_ROOTS = ("risk", "analytics", "report", "runner", "engine.backtester")


def assert_no_forbidden_imports(module_path: Path) -> None:
    """Statically parses module_path's source and raises AssertionError if
    it imports anything under FORBIDDEN_IMPORT_ROOTS. Does not import or
    execute the module."""
```

`GenerateSignals` is a documentation/type-checking aid — every future
strategy module's `generate_signals` function should match this shape.
`Signal` is imported directly from `engine.models` and returned as-is (a
plain data contract — id/timestamp/direction/stop/target — with no
execution, sizing, fee, or slippage fields), matching the precedent set by
the existing reference implementation.

`assert_no_forbidden_imports` uses `ast.parse` on the module's source text
and walks the entire tree for `Import`/`ImportFrom` nodes — including ones
nested inside function bodies, not just module-level statements — checking
each imported dotted path against `FORBIDDEN_IMPORT_ROOTS` (prefix match,
so `engine.backtester` blocks `from engine.backtester import run` but
`engine.models` remains unaffected). It never imports or executes the
target module — pure static source analysis.

## The Central Architecture Test (`tests/strategies/test_architecture.py`)

```python
from pathlib import Path

from strategies.contracts import assert_no_forbidden_imports

STRATEGIES_DIR = Path(__file__).resolve().parents[2] / "strategies"


def test_no_strategy_module_imports_forbidden_packages() -> None:
    for path in STRATEGIES_DIR.glob("*.py"):
        if path.name in ("__init__.py", "contracts.py"):
            continue
        assert_no_forbidden_imports(path)
```

This single test automatically scans every `.py` file added to
`strategies/` (except the package's own `__init__.py` and `contracts.py`)
on every test run. Today it iterates zero files and passes trivially; the
moment a future milestone adds `strategies/ema_cross.py`, this same test
starts covering it with no edits required anywhere.

## Reproducibility Rules (documented convention, not automated)

- Every tunable value (period, threshold, multiplier) is a module-level
  constant in the strategy's own file — never a function parameter,
  config value, or CLI flag.
- `generate_signals` is a pure function of `ohlcv`: no randomness, no
  wall-clock time, no I/O, no external state — the same input always
  produces the same output.
- Every value used to decide row `i`'s signal depends only on rows
  `<= i`. Each future strategy's own test suite is expected to include a
  look-ahead regression test, following the precedent set by
  `test_ema_trend_pullback.py::test_generate_signals_look_ahead_regression`.

## Testing Strategy (for this milestone only)

- `test_architecture.py`: the central import-boundary test described
  above, plus its own unit coverage for `assert_no_forbidden_imports`
  itself — using small temporary `.py` files written to `tmp_path`
  (one importing `risk`, one importing `engine.backtester`, one importing
  only `engine.models` and `polars`) to confirm the checker correctly
  passes clean modules and fails forbidden ones, independent of whatever
  real strategy modules exist at the time.

## Known Limitations

- The forbidden-import list is scoped exactly to what was asked (position
  sizing/leverage → `risk`; execution → `engine.backtester`; reporting →
  `report`; orchestration → `runner`; analytics → `analytics`). It does
  not block `engine.loader` or `data.*` — those concern reading OHLCV
  data, not sizing/fees/execution/reporting, and were not listed among the
  forbidden concerns. A strategy has no practical reason to import them
  (it already receives `ohlcv` as a parameter), so this is left
  unenforced rather than over-restricted.
- Static AST analysis cannot catch indirect violations (e.g. a strategy
  importing a third, innocuous-looking helper module that itself imports
  `risk`). This is judged an acceptable gap for a research-framework
  convention check, not a security boundary.

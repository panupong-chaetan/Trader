# strategies — Strategy Research Framework

A minimal scaffold so future research strategies can each be added as a
single new module, sharing one contract. This package currently contains
no concrete strategies — the archived reference implementation
(`strategy/ema_trend_pullback.py`) is unaffected and lives separately.

## The contract

Every strategy module exposes exactly one public function:

```python
def generate_signals(ohlcv: pl.DataFrame) -> list[Signal]:
    ...
```

`Signal` is `engine.models.Signal` — a plain data contract
(id/timestamp/direction/stop/target) with no execution, sizing, fee, or
slippage fields. `contracts.py` defines this shape as
`GenerateSignals = Callable[[pl.DataFrame], list[Signal]]`.

## What a strategy must never know about

Position sizing, leverage, fees, slippage, execution, reports, or
analytics. A strategy receives only `ohlcv` and returns only `Signal`
objects — nothing else. `contracts.py`'s `assert_no_forbidden_imports`
statically checks a module's source for imports of `risk`, `analytics`,
`report`, `runner`, or `engine.backtester`. One central test,
`tests/strategies/test_architecture.py::test_no_strategy_module_imports_forbidden_packages`,
automatically scans every `.py` file in this package against that rule —
adding a new strategy file gets covered with no extra test to write.

## Reproducibility rules

- Every tunable value is a module-level constant in the strategy's own
  file — never a function parameter, config value, or CLI flag.
- `generate_signals` is a pure function of `ohlcv`: no randomness, no
  wall-clock time, no I/O, no external state.
- A row `i`'s signal decision depends only on rows `<= i`. Each strategy's
  own test suite should include a look-ahead regression test, following
  the precedent in `strategy/test_ema_trend_pullback.py`.

## Adding a new strategy

Create one new file in this package (e.g. `strategies/ema_cross.py`)
implementing `generate_signals`, plus that strategy's own normal test file
verifying its specific signal logic — nothing else needs to change. No
registry or runner wiring exists yet; strategies are imported explicitly
wherever they're used.

Examples of the *kind* of strategy this framework is meant to support
(illustrative only, not a committed roadmap): EMA Cross, Breakout,
Donchian, Bollinger Bands, RSI Mean Reversion, MACD, ADX Trend,
Supertrend, Liquidity Sweep, Fair Value Gap, ICT, Smart Money Concepts.

See `docs/superpowers/specs/2026-08-01-strategy-research-framework-design.md`.

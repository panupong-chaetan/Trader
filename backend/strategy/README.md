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

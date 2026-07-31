# runner — Backtest Runner CLI

Orchestration only: `engine.loader` -> `strategy.ema_trend_pullback` ->
`engine.backtester` -> `report`. No simulation or report-calculation logic
lives here.

```
python -m backend.runner.cli \
  --symbol BTC/USDT --timeframe 15m --exchange binance \
  --output-dir ./reports \
  [--allow-incomplete-dataset] \
  [--initial-capital 10000] [--leverage 1.0] \
  [--risk-per-trade-pct 0.005] [--fee-pct 0.001] [--slippage-pct 0.0005]
```

Every run writes to a new `run_<timestamp>_<uuid8>/` subdirectory under
`--output-dir` — previous reports are never overwritten. No flags exist for
EMA/ATR/R-multiple — those are fixed inside the strategy module.

See `docs/superpowers/specs/2026-07-31-backtest-runner-report-design.md`.

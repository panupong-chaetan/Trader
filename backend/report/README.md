# report — Backtest Report Builder and Export

Pure reporting logic, no simulation code. Consumes `engine.models.BacktestResult`.

- `builder.py` — `build_summary(result, num_signals, symbol, timeframe, exchange) -> ReportSummary`.
  Computes dataset range/quality, gap-overlap warnings, equity/PnL,
  fee totals, exit-reason counts. Read-only over `BacktestResult` — never
  calls the simulation engine.
- `export.py` — `write_summary_json`, `write_trades_csv` (explicit schema,
  so a zero-trade result still writes a correctly-headered CSV),
  `write_equity_curve_parquet`.

See `docs/superpowers/specs/2026-07-31-backtest-runner-report-design.md`.

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

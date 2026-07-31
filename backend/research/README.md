# research — Strategy Research Database

Records one immutable, factual experiment result per completed backtest
and provides a side-by-side comparison across every recorded experiment.
This module never runs a backtest and never ranks, optimizes, or
recommends a strategy — it only stores and displays what already
happened.

## Modules

- `models.py` — `StrategyCatalogRecord`, a frozen (immutable) Pydantic
  record.
- `catalog.py` — `register_strategy_result()` writes one new JSON file
  per experiment (never rewrites an existing one); `load_catalog()`
  reads every record back, ordered by `created_at`.
- `comparison.py` — `compare_strategies()` builds a `polars.DataFrame`
  with columns `strategy_name, category, profit_factor, sharpe_ratio,
  expectancy, max_drawdown, total_trades, total_return`, ordered by
  `created_at` — never by any performance metric.
- `export.py` — `export_catalog_csv()` / `export_catalog_json()` dump
  every field of every record to a file. Unlike the per-experiment
  catalog files, an export file is a disposable snapshot and may be
  overwritten on each call.

## Registering a result

`register_strategy_result()` takes a `report.builder.ReportSummary`
(read-only import — this module never modifies `report/`) plus
`strategy_name`, `category`, `hypothesis`, and `report_directory`, which
`ReportSummary` does not carry. Call it explicitly after a backtest run
completes:

```python
from pathlib import Path
from report.builder import build_summary
from research.catalog import register_strategy_result

summary = build_summary(result, num_signals=42, symbol="BTC/USDT", timeframe="15m", exchange="binance")
register_strategy_result(
    summary=summary,
    strategy_name="donchian_breakout",
    category="breakout",
    hypothesis="Closes beyond a 20-period channel continue in that direction.",
    report_directory=Path("reports/run_20260801T120000_abcd1234"),
    catalog_dir=Path("research/catalog"),
)
```

See `docs/superpowers/specs/2026-08-01-strategy-research-database-design.md`.

# research/dashboard — Research Dashboard

A read-only CLI viewer over the Strategy Research Database
(`research/catalog/`). It never writes to the catalog — sorting is
display-only, and filtering never removes a stored record, only what is
shown.

## Modules

- `filters.py` — `filter_records()`: normalized substring match on
  category / market / timeframe.
- `sorting.py` — `sort_records()` + `SORT_FIELDS`: display-order only,
  descending by default, `None`-valued records always last.
- `table.py` — `build_dashboard_table()`: the 14-column human-readable
  table.
- `stats.py` — `compute_summary_stats()`: experiment count, averages,
  and (only when a metric is explicitly given) the best experiment by
  that metric.
- `export.py` — `export_table_csv()` / `export_table_markdown()`.
- `cli.py` — `main()`: wires the above into a single command.

## Usage

```bash
python -m research.dashboard.cli
python -m research.dashboard.cli --category trend --sort profit_factor
python -m research.dashboard.cli --market BTCUSDT --timeframe 15m --order asc
python -m research.dashboard.cli --sort sharpe --export-csv out.csv --export-markdown out.md
```

See `docs/superpowers/specs/2026-08-01-research-dashboard-design.md`.

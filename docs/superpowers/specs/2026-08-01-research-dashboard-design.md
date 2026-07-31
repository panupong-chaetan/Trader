# Research Dashboard — Milestone Design

Date: 2026-08-01
Project: Trader v2 — Phase 2
Milestone: Research Dashboard

## Overview

A read-only dashboard over the Strategy Research Database
(`backend/research/`). It loads every catalog record, and lets the user
filter, sort (for display only), summarize, and export what's already
there. It never computes a backtest, never mutates a catalog record, and
never stores a ranking or recommendation — it is a viewer, not an
analysis engine.

## Goals

- Load every experiment record via the existing, unmodified
  `research.catalog.load_catalog()`.
- Display a 14-column human-readable comparison table.
- Support filtering by category / market / timeframe.
- Support sorting the displayed table by any recognized metric
  (display-only — the underlying catalog files are never touched).
- Compute summary statistics (experiment count, average profit factor,
  average Sharpe, average max drawdown, best experiment by a selected
  metric).
- Export the displayed table as CSV and Markdown.
- Provide a CLI entry point, matching the shape of `runner/cli.py`.
- Demonstrate the dashboard against the two existing historical runs
  (EMA Trend Pullback, Donchian Breakout), registered into the catalog
  first since they predate the Research Database milestone.

## Non-Goals

- No optimization, no stored ranking, no AI/ML, no automatic strategy
  recommendation.
- No mutation of any file under `research/catalog/` — `register_strategy_result()`
  is called exactly once per historical run during the demonstration
  step, and never again by the dashboard itself.
- No changes whatsoever to `data/`, `engine/`, `risk/`, `analytics/`,
  `report/`, `runner/`, `diagnostics/`, `strategy/` (archived),
  `strategies/`, or any existing file under `research/` (`models.py`,
  `catalog.py`, `comparison.py`, `export.py`). `dashboard/` only imports
  `research.catalog.load_catalog` and `research.models.StrategyCatalogRecord`
  as read-only dependencies.
- No web UI / server — this is a CLI tool, consistent with every other
  entry point in this project so far.

## Architecture

```
Trader_v2/
  backend/
    research/
      dashboard/
        __init__.py
        filters.py        # filter_records()
        sorting.py            # sort_records(), SORT_FIELDS
        table.py                 # build_dashboard_table()
        stats.py                    # compute_summary_stats(), SummaryStats
        export.py                      # export_table_csv(), export_table_markdown()
        cli.py                            # build_parser(), main()
        README.md
    tests/
      research/
        dashboard/
          __init__.py
          test_filters.py
          test_sorting.py
          test_table.py
          test_stats.py
          test_export.py
          test_cli.py
```

`research/comparison.py` is not reused by the dashboard: it returns 8
machine-facing columns, but the dashboard's table needs 14 human-facing
ones (`Hypothesis`, `Market`, `Timeframe`, `Win Rate`, `Fees`,
`Created At` are not present in `compare_strategies()`'s output).
`dashboard/table.py` builds its own `pl.DataFrame` directly from
`list[StrategyCatalogRecord]`, independently of `comparison.py`.

## Filtering (`dashboard/filters.py`)

```python
def filter_records(
    records: list[StrategyCatalogRecord],
    category: str | None = None,
    market: str | None = None,
    timeframe: str | None = None,
) -> list[StrategyCatalogRecord]: ...
```

Matching is **normalized substring**: both the typed filter value and the
stored field are lowercased and stripped of every character except
letters and digits before a substring check
(`_normalize("BTC/USDT") == "btcusdt"`, `_normalize("trend_following") ==
"trendfollowing"`). `--category trend` therefore matches
`"trend_following"`; `--market BTCUSDT` matches `"BTC/USDT"`. Each
provided filter narrows the result independently (AND semantics); an
omitted filter passes every record through unchanged.

## Sorting (`dashboard/sorting.py`)

```python
SORT_FIELDS: dict[str, str] = {
    "profit_factor": "profit_factor",
    "sharpe": "sharpe_ratio",
    "expectancy": "expectancy",
    "win_rate": "win_rate",
    "max_drawdown": "max_drawdown",
    "total_return": "total_return",
    "trades": "total_trades",
    "fees": "total_fees",
    "created_at": "created_at",
    "strategy": "strategy_name",
    "category": "category",
}

def sort_records(
    records: list[StrategyCatalogRecord],
    sort_key: str | None,
    descending: bool = True,
) -> list[StrategyCatalogRecord]: ...
```

With `sort_key=None`, records are ordered by `created_at`. Any other
`sort_key` must be a key of `SORT_FIELDS` (an unrecognized key raises
`ValueError`, caught by the CLI and reported as a usage error). Sorting
is descending by default (`--order desc`), reversible with `--order asc`.
Records whose sorted field is `None` are always placed after every
record with a value, in both directions, since a null can't be
meaningfully ranked against a number — it is neither "first" nor "last"
in a value sense, so it goes last unconditionally. Sorting only decides
the order returned to the caller; it never opens or rewrites a catalog
file (`load_catalog()`/`register_strategy_result()` in `research/catalog.py`
are the only functions with file access, and this module never calls
`register_strategy_result()`).

## Table (`dashboard/table.py`)

```python
def build_dashboard_table(records: list[StrategyCatalogRecord]) -> pl.DataFrame: ...
```

Produces exactly these columns, in this order:
`Strategy, Category, Hypothesis, Market, Timeframe, Profit Factor,
Sharpe, Expectancy, Win Rate, Max Drawdown, Total Return, Trades, Fees,
Created At`. Row order is whatever order the input list is already in —
callers are expected to filter/sort first (via `filters.py`/`sorting.py`)
and pass the already-ordered list in.

## Summary statistics (`dashboard/stats.py`)

```python
@dataclass(frozen=True)
class SummaryStats:
    total_experiments: int
    avg_profit_factor: float | None
    avg_sharpe: float | None
    avg_max_drawdown: float | None
    best_experiment_metric: str | None
    best_experiment: StrategyCatalogRecord | None

def compute_summary_stats(
    records: list[StrategyCatalogRecord],
    best_metric: str | None,
) -> SummaryStats: ...
```

Computed over the **filtered** set (order-independent — computing stats
before or after sorting gives the same result). `avg_profit_factor`,
`avg_sharpe` (from `sharpe_ratio`), and `avg_max_drawdown` are the mean
of non-null values only; `None` if every value in the set is null or the
set is empty.

Per your explicit correction: **`best_experiment` has no implicit
default metric.** If `best_metric` is `None` (i.e. the CLI's `--sort` was
not given), `best_experiment_metric` and `best_experiment` are both
`None` — reported as `N/A` by the CLI. If `best_metric` is provided, it
must be a key of `SORT_FIELDS`; `best_experiment` is the record with the
highest value of that field among records with a non-null value (ties
broken by keeping the first one encountered in the input order); `None`
if no record in the set has a value for that metric.

## Export (`dashboard/export.py`)

```python
def export_table_csv(df: pl.DataFrame, path: Path) -> None
def export_table_markdown(df: pl.DataFrame, path: Path) -> None
```

`export_table_csv` uses `pl.DataFrame.write_csv` directly. Polars has no
built-in Markdown writer, so `export_table_markdown` hand-builds a
GitHub-flavored pipe table (header row, `---` separator row, one row per
record) from the same `pl.DataFrame`. Both take the already-built,
already-filtered-and-sorted display table — the same "disposable
snapshot, safe to overwrite" semantics as `research/export.py`'s exports.

## CLI (`dashboard/cli.py`)

Same shape as `runner/cli.py`: `build_parser() -> argparse.ArgumentParser`
and `main(argv: list[str] | None = None) -> int`.

| Flag | Default | Notes |
|---|---|---|
| `--catalog-dir` | `Trader_v2/research/catalog` | `Path`, same `parents[N]`-derived default pattern as `runner.cli.DEFAULT_DATA_DIR` |
| `--category` | `None` | passed to `filter_records` |
| `--market` | `None` | passed to `filter_records` |
| `--timeframe` | `None` | passed to `filter_records` |
| `--sort` | `None` | must be a `SORT_FIELDS` key if given |
| `--order` | `desc` | `asc` or `desc` |
| `--export-csv` | `None` | `Path`; if given, writes the displayed table there |
| `--export-markdown` | `None` | `Path`; if given, writes the displayed table there |

`main()` pipeline: `load_catalog(catalog_dir)` → `filter_records(...)` →
`sort_records(..., sort_key=args.sort, descending=(args.order != "asc"))`
→ `build_dashboard_table(...)` (printed to stdout) →
`compute_summary_stats(filtered_records, best_metric=args.sort)`
(printed to stdout) → optional `export_table_csv`/`export_table_markdown`
if the corresponding flag was given. An unrecognized `--sort` value is
caught (`ValueError` from `sort_records`) and reported via `logger.error`,
returning exit code `1`, matching `runner.cli.main`'s error-handling
convention.

## Demonstration Plan (workflow step 6)

Confirmed mapping:
- `reports/run_20260731T143348_de3fb080` → EMA Trend Pullback, category `trend_following`
- `reports/run_20260731T174825_bc6cd6d5` → Donchian Breakout, category `trend_following`

Both runs predate the Research Database milestone, so neither has a
catalog record yet. As a one-time step (not part of the dashboard module
itself), each run's `summary.json` is loaded back into a `ReportSummary`-
shaped call to `register_strategy_result()` exactly once, producing
exactly two new files under `research/catalog/`. This uses only the
existing, unmodified `research.catalog.register_strategy_result()` — no
new registration logic is added anywhere. After registration, the
dashboard CLI is run against the real two-record catalog to demonstrate
loading, filtering, sorting, summary stats, and both export formats.

## Testing Strategy

- `test_filters.py`: exact match still passes; substring/normalized
  matches across `/`, `_`, case; combined filters (AND); no filters
  passes everything through unchanged; a filter matching nothing returns
  `[]`.
- `test_sorting.py`: default (`sort_key=None`) orders by `created_at`;
  each `SORT_FIELDS` entry sorts correctly ascending and descending;
  `None`-valued records always sort last in both directions; unknown
  `sort_key` raises `ValueError`.
- `test_table.py`: column names and order match the spec exactly for a
  non-empty input; empty input produces an empty `pl.DataFrame` with the
  same columns.
- `test_stats.py`: `total_experiments` count; averages skip nulls and
  are `None` when all-null; `best_metric=None` → `best_experiment` and
  `best_experiment_metric` are both `None`; `best_metric` given → correct
  best record, ties keep first-encountered, `None` when no record has
  that metric.
- `test_export.py`: CSV round-trips via `csv.DictReader`; Markdown output
  has a header row, a `---` separator row, and one data row per record,
  with correct column values.
- `test_cli.py`: end-to-end against a `tmp_path` catalog directory
  (register a couple of `StrategyCatalogRecord`s via
  `research.catalog.register_strategy_result` or by writing JSON files
  directly) — filters/sorts/exports produce the expected output; an
  unrecognized `--sort` returns exit code `1` without raising.

## Known Limitations

- `--sort`/`SORT_FIELDS` covers a fixed, explicit set of metrics
  (matching the milestone's examples plus the remaining table columns).
  Free-text sorting by an arbitrary `StrategyCatalogRecord` field name is
  out of scope — YAGNI until a concrete need for it appears.
- Filter matching normalizes away all punctuation, so `--market usdt`
  would also match a hypothetical `"EURUSDT"` market — accepted as a
  reasonable tradeoff for the flexibility the milestone's own examples
  require (`BTCUSDT` matching `"BTC/USDT"`).

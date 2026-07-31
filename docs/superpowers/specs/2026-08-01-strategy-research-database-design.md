# Strategy Research Database — Milestone Design

Date: 2026-08-01
Project: Trader v2 — Phase 2
Milestone: Strategy Research Database

## Overview

A research layer that lets every future strategy be evaluated
consistently against every other one. This milestone does not run
backtests, compute metrics, or implement any trading strategy — it only
records already-computed results (`report.builder.ReportSummary`) as
immutable catalog entries, and produces a side-by-side comparison of
whatever has been recorded so far. It builds on the contract established
by the [Strategy Research Framework](2026-08-01-strategy-research-framework-design.md)
milestone but is otherwise independent of it.

## Goals

- Provide `register_strategy_result()` to file away one immutable
  experiment record per completed backtest run.
- Provide `load_catalog()` to read back every recorded experiment.
- Provide `compare_strategies()` to build a side-by-side comparison table
  of all recorded experiments.
- Provide `export_catalog_csv()` / `export_catalog_json()` to export the
  full catalog.
- Guarantee the catalog is append-only: registering a new result can
  never overwrite, mutate, or delete a previously recorded one.

## Non-Goals

- No optimization, no ranking by performance, no automatic
  recommendation of a "best" strategy, no AI/ML — this module stores and
  displays factual results only.
- No implementation of any trading strategy.
- No registry or auto-discovery of strategies (separate concern already
  scoped out of the Strategy Research Framework milestone).
- No CLI/runner wiring. `register_strategy_result()` is called explicitly
  by whoever ran the backtest, the same way strategies are imported
  explicitly today.
- No changes whatsoever to `data/`, `engine/`, `risk/`, `analytics/`,
  `report/`, `runner/`, `diagnostics/`, `strategy/` (archived), or
  `strategies/`. `research/` only *imports* `report.builder.ReportSummary`
  as a read-only type; the dependency direction is
  `report -> research consumer` and must never run the other way —
  `report/` must not import anything from `research/`.

## Architecture

```
Trader_v2/
  backend/
    research/
      __init__.py
      models.py          # StrategyCatalogRecord (Pydantic, frozen)
      catalog.py            # register_strategy_result(), load_catalog()
      comparison.py            # compare_strategies()
      export.py                    # export_catalog_csv(), export_catalog_json()
      README.md
    tests/
      research/
        __init__.py
        test_models.py
        test_catalog.py
        test_comparison.py
        test_export.py
  research/
    catalog/                  # experiment record JSON files live here (data, not code)
```

`Trader_v2/research/catalog/` is a new top-level data directory, mirroring
the existing separation between a module's code (`backend/data/`,
`backend/report/`) and its output (`Trader_v2/data/`, `Trader_v2/reports/`).
Every `research/` function takes the catalog directory as an explicit
`Path` parameter — nothing is hardcoded inside the logic — so tests use
`tmp_path` and no function silently depends on process working directory.

## Data Model (`research/models.py`)

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class StrategyCatalogRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str          # unique id; also the record's filename stem
    strategy_name: str
    category: str                 # free-form, e.g. "trend_following", "breakout"
    hypothesis: str                 # short human-readable description of what's being tested
    market: str                       # e.g. "BTC/USDT"
    timeframe: str
    start_date: datetime                # dataset range actually simulated
    end_date: datetime
    initial_capital: float
    total_signals: int
    total_trades: int
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_return: float                   # % return
    total_fees: float
    rejected_signals: int
    report_directory: str                   # path to that run's reports/run_.../ for traceability
    created_at: datetime                      # when this record was registered
```

`frozen=True` makes every instance genuinely immutable after
construction — Pydantic raises on any attempted field assignment, so
"immutable research record" is enforced by the type itself, not just by
convention.

`experiment_id` is generated as
`f"{strategy_name}_{created_at:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"`,
matching the timestamp+short-uuid shape `runner.cli._create_run_directory`
already uses for run directories elsewhere in this codebase. It is unique
per registration (even for repeat backtests of the same strategy) and
doubles as the record's filename stem, so a record can always be located
either by scanning the catalog in memory or by its filename on disk.

## Append-Only Storage (`research/catalog.py`)

```python
def register_strategy_result(
    summary: ReportSummary,        # report.builder.ReportSummary — read-only import
    strategy_name: str,
    category: str,
    hypothesis: str,
    report_directory: Path,
    catalog_dir: Path,
) -> StrategyCatalogRecord: ...

def load_catalog(catalog_dir: Path) -> list[StrategyCatalogRecord]: ...
```

**Why one JSON file per record, not one shared file:** append-only is
made a filesystem property rather than a coding discipline.
`register_strategy_result()` only ever calls `Path.write_text()` on a
brand-new path (`catalog_dir / f"{experiment_id}.json"`); it never opens
an existing catalog file for reading-then-rewriting. There is structurally
no code path in this module that can touch a previously written record.
If the target file somehow already exists (a UUID collision, effectively
impossible at this scale), `register_strategy_result()` raises rather
than silently overwriting.

**Field mapping** from `ReportSummary` (fields it does not carry —
`strategy_name`, `category`, `hypothesis`, `report_directory` — come from
the explicit parameters instead):

| `StrategyCatalogRecord` field | Source |
|---|---|
| `market` | `summary.symbol` |
| `timeframe` | `summary.timeframe` |
| `start_date` | `summary.dataset_start` |
| `end_date` | `summary.dataset_end` |
| `initial_capital` | `summary.config.initial_capital` |
| `total_signals` | `summary.num_signals` |
| `total_trades` | `summary.num_trades` |
| `rejected_signals` | `summary.num_rejected_signals` |
| `win_rate`, `profit_factor`, `expectancy`, `sharpe_ratio` | pass through as-is |
| `max_drawdown` | `summary.max_drawdown_pct` |
| `total_return` | `summary.return_pct` |
| `total_fees` | `summary.total_fees_paid` |
| `created_at` | `datetime.now(timezone.utc)` at call time |

`load_catalog()` glob-reads every `*.json` file under `catalog_dir`,
parses each into a `StrategyCatalogRecord`, and returns the list ordered
by `created_at`. A file that fails to parse is a hard failure (raises),
consistent with this project's existing "no silent data problems"
precedent (e.g. `engine.loader` on gap/quality issues) — a corrupt record
is a data integrity problem, not something to skip past quietly.

## Comparison Table (`research/comparison.py`)

```python
def compare_strategies(records: list[StrategyCatalogRecord]) -> pl.DataFrame: ...
```

Pure function, no I/O — the caller loads records first via
`load_catalog()`. Returns a `pl.DataFrame` with exactly these columns, in
this order: `strategy_name, category, profit_factor, sharpe_ratio,
expectancy, max_drawdown, total_trades, total_return`. Rows are ordered by
`created_at` (registration order) — never by any performance column, so
the table itself cannot be read as an implicit ranking.

## Export (`research/export.py`)

```python
def export_catalog_csv(records: list[StrategyCatalogRecord], path: Path) -> None: ...
def export_catalog_json(records: list[StrategyCatalogRecord], path: Path) -> None: ...
```

Both export the **full** record (every `StrategyCatalogRecord` field, not
just the 8-column comparison subset). Unlike the per-record files under
`catalog/`, an export file is a derived, disposable snapshot — it is fine,
and expected, for `path` to be overwritten on repeated calls. This does
not conflict with the append-only rule: the rule protects the source-of-
truth records in `catalog/`, not convenience exports generated from them.

## Testing Strategy

- `test_models.py`: constructing a `StrategyCatalogRecord` and asserting
  attribute assignment raises (frozen); required-field validation.
- `test_catalog.py`:
  - `register_strategy_result()` writes exactly one new file per call, and
    a second registration does not alter the first file's content
    (byte-for-byte comparison before/after).
  - registering the same strategy twice produces two distinct
    `experiment_id`s and two files.
  - `load_catalog()` round-trips a written record back to an equal
    `StrategyCatalogRecord`, and returns records ordered by `created_at`.
  - `load_catalog()` raises on a malformed JSON file in the directory.
  - field-mapping test: build a `ReportSummary`, call
    `register_strategy_result()`, assert every mapped field matches
    Table above.
- `test_comparison.py`: `compare_strategies()` produces the exact 8
  columns in the exact order, ordered by `created_at`, over a
  hand-built list of records (including one with `None` metrics, to
  confirm nulls pass through rather than being coerced to 0 or dropped).
- `test_export.py`: `export_catalog_csv()`/`export_catalog_json()` write
  all fields for all records; a second export call overwrites the
  previous export file without error.

## Known Limitations

- `load_catalog()` fails hard on any single corrupt file rather than
  skipping it — appropriate for a small, single-user research catalog,
  but would need reconsideration if the catalog were ever written to
  concurrently by multiple processes.
- No indexing or query layer — `load_catalog()` always reads every file
  in `catalog_dir`. Fine at research-catalog scale; would need revisiting
  if the catalog grows into the thousands of records.
- `category` and `hypothesis` are free-form strings with no fixed
  taxonomy — deliberate, to avoid guessing a classification scheme ahead
  of having enough real strategies to know what categories are needed.

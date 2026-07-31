# Research Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `backend/research/dashboard/` module — a read-only CLI viewer over the Strategy Research Database that filters, sorts (display-only), summarizes, and exports the catalog, without modifying any existing module including `research/`'s own `models.py`/`catalog.py`/`comparison.py`/`export.py`.

**Architecture:** Five small, single-responsibility files (`filters.py`, `sorting.py`, `table.py`, `stats.py`, `export.py`) plus a thin `cli.py` wiring them together — built in that dependency order, each with its own test file, strict TDD (failing test first). A final demonstration task registers the two pre-existing historical runs into the catalog (one-time, using the unmodified `research.catalog.register_strategy_result`) and runs the CLI against them.

**Tech Stack:** Python 3.12, Polars (table + CSV export), stdlib `argparse`/`logging`, pytest.

## Global Constraints

- Do not modify any file under `data/`, `engine/`, `risk/`, `analytics/`, `report/`, `runner/`, `diagnostics/`, `strategy/`, `strategies/`, or any existing file under `research/` (`models.py`, `catalog.py`, `comparison.py`, `export.py`) — `dashboard/` only imports `research.catalog.load_catalog`, `research.catalog.register_strategy_result` (demo step only), and `research.models.StrategyCatalogRecord`.
- Sorting is display-only — `sort_records` never writes anything; only `research.catalog.register_strategy_result` may create a catalog file, and only during the one-time demonstration step.
- Filter matching is normalized substring (lowercase, strip everything but letters/digits) per the approved design.
- `--sort` is always descending by default (`--order asc` to reverse); records with a `None` value for the sorted field always sort last, in both directions.
- `best_experiment` in summary stats is `None`/`N/A` whenever `--sort` was not given — no implicit default metric.
- Pure Python, type hints on every function signature, `logging` (never bare `print` for diagnostics — user-facing table/stats output uses `print`, matching a CLI's normal stdout contract), one unit test file per module.
- Reference design: `docs/superpowers/specs/2026-08-01-research-dashboard-design.md`.

---

## Task 1: Package scaffolding + `filter_records`

**Files:**
- Create: `backend/research/dashboard/__init__.py` (empty)
- Create: `backend/research/dashboard/filters.py`
- Create: `backend/tests/research/dashboard/__init__.py` (empty)
- Test: `backend/tests/research/dashboard/test_filters.py`

**Interfaces:**
- Produces: `research.dashboard.filters.filter_records(records: list[StrategyCatalogRecord], category: str | None = None, market: str | None = None, timeframe: str | None = None) -> list[StrategyCatalogRecord]`.

- [ ] **Step 1: Create empty package `__init__.py` files**

Create `backend/research/dashboard/__init__.py` (empty) and `backend/tests/research/dashboard/__init__.py` (empty).

- [ ] **Step 2: Write the failing test file**

Create `backend/tests/research/dashboard/test_filters.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from research.dashboard.filters import filter_records
from research.models import StrategyCatalogRecord


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="trend_following",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=10,
        total_trades=8,
        win_rate=0.5,
        profit_factor=1.4,
        expectancy=5.0,
        sharpe_ratio=0.8,
        max_drawdown=0.1,
        total_return=4.2,
        total_fees=20.0,
        rejected_signals=2,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return StrategyCatalogRecord(**base)


def test_filter_records_returns_everything_with_no_filters() -> None:
    records = [_record(), _record(experiment_id="b")]

    assert filter_records(records) == records


def test_filter_records_matches_category_by_substring() -> None:
    records = [_record(category="trend_following"), _record(experiment_id="b", category="mean_reversion")]

    result = filter_records(records, category="trend")

    assert len(result) == 1
    assert result[0].category == "trend_following"


def test_filter_records_matches_market_ignoring_slash_and_case() -> None:
    records = [_record(market="BTC/USDT")]

    result = filter_records(records, market="btcusdt")

    assert result == records


def test_filter_records_matches_timeframe_exact() -> None:
    records = [_record(timeframe="15m"), _record(experiment_id="b", timeframe="1h")]

    result = filter_records(records, timeframe="15m")

    assert len(result) == 1
    assert result[0].timeframe == "15m"


def test_filter_records_combines_filters_with_and_semantics() -> None:
    records = [
        _record(category="trend_following", market="BTC/USDT"),
        _record(experiment_id="b", category="trend_following", market="ETH/USDT"),
    ]

    result = filter_records(records, category="trend", market="btc")

    assert len(result) == 1
    assert result[0].market == "BTC/USDT"


def test_filter_records_returns_empty_list_when_nothing_matches() -> None:
    records = [_record()]

    result = filter_records(records, category="mean_reversion")

    assert result == []
```

- [ ] **Step 3: Run the test to verify it fails**

Run (from `backend/`): `pytest tests/research/dashboard/test_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.dashboard.filters'` (or `research.dashboard`).

- [ ] **Step 4: Write the minimal implementation**

Create `backend/research/dashboard/filters.py`:

```python
from __future__ import annotations

import re

from research.models import StrategyCatalogRecord

_NORMALIZE_RE = re.compile(r"[^a-z0-9]")


def _normalize(value: str) -> str:
    return _NORMALIZE_RE.sub("", value.lower())


def filter_records(
    records: list[StrategyCatalogRecord],
    category: str | None = None,
    market: str | None = None,
    timeframe: str | None = None,
) -> list[StrategyCatalogRecord]:
    filtered = records
    if category is not None:
        needle = _normalize(category)
        filtered = [r for r in filtered if needle in _normalize(r.category)]
    if market is not None:
        needle = _normalize(market)
        filtered = [r for r in filtered if needle in _normalize(r.market)]
    if timeframe is not None:
        needle = _normalize(timeframe)
        filtered = [r for r in filtered if needle in _normalize(r.timeframe)]
    return filtered
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/research/dashboard/test_filters.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/research/dashboard/__init__.py backend/research/dashboard/filters.py backend/tests/research/dashboard/__init__.py backend/tests/research/dashboard/test_filters.py
git commit -m "feat(research-dashboard): add filter_records"
```

---

## Task 2: `sort_records`

**Files:**
- Create: `backend/research/dashboard/sorting.py`
- Test: `backend/tests/research/dashboard/test_sorting.py`

**Interfaces:**
- Produces: `research.dashboard.sorting.SORT_FIELDS: dict[str, str]` and `research.dashboard.sorting.sort_records(records: list[StrategyCatalogRecord], sort_key: str | None, descending: bool = True) -> list[StrategyCatalogRecord]`. Task 4 (`stats.py`) imports `SORT_FIELDS`; Task 6 (`cli.py`) imports both.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/dashboard/test_sorting.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research.dashboard.sorting import SORT_FIELDS, sort_records
from research.models import StrategyCatalogRecord


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="trend_following",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=10,
        total_trades=8,
        win_rate=0.5,
        profit_factor=1.4,
        expectancy=5.0,
        sharpe_ratio=0.8,
        max_drawdown=0.1,
        total_return=4.2,
        total_fees=20.0,
        rejected_signals=2,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return StrategyCatalogRecord(**base)


def test_sort_records_defaults_to_created_at_descending() -> None:
    older = _record(experiment_id="a", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _record(experiment_id="b", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))

    result = sort_records([older, newer], sort_key=None)

    assert [r.experiment_id for r in result] == ["b", "a"]


def test_sort_records_by_profit_factor_descending() -> None:
    low = _record(experiment_id="a", profit_factor=1.0)
    high = _record(experiment_id="b", profit_factor=2.0)

    result = sort_records([low, high], sort_key="profit_factor")

    assert [r.experiment_id for r in result] == ["b", "a"]


def test_sort_records_ascending_when_requested() -> None:
    low = _record(experiment_id="a", profit_factor=1.0)
    high = _record(experiment_id="b", profit_factor=2.0)

    result = sort_records([high, low], sort_key="profit_factor", descending=False)

    assert [r.experiment_id for r in result] == ["a", "b"]


def test_sort_records_places_none_values_last_in_both_directions() -> None:
    has_value = _record(experiment_id="a", sharpe_ratio=1.0)
    no_value = _record(experiment_id="b", sharpe_ratio=None)

    desc = sort_records([no_value, has_value], sort_key="sharpe", descending=True)
    asc = sort_records([no_value, has_value], sort_key="sharpe", descending=False)

    assert [r.experiment_id for r in desc] == ["a", "b"]
    assert [r.experiment_id for r in asc] == ["a", "b"]


def test_sort_records_raises_on_unknown_key() -> None:
    with pytest.raises(ValueError):
        sort_records([_record()], sort_key="not_a_real_metric")


def test_sort_fields_covers_expected_metrics() -> None:
    assert set(SORT_FIELDS) == {
        "profit_factor", "sharpe", "expectancy", "win_rate", "max_drawdown",
        "total_return", "trades", "fees", "created_at", "strategy", "category",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/dashboard/test_sorting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.dashboard.sorting'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/dashboard/sorting.py`:

```python
from __future__ import annotations

from research.models import StrategyCatalogRecord

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
) -> list[StrategyCatalogRecord]:
    if sort_key is None:
        field = "created_at"
    elif sort_key in SORT_FIELDS:
        field = SORT_FIELDS[sort_key]
    else:
        raise ValueError(f"unknown sort key: {sort_key!r}")

    with_value = [r for r in records if getattr(r, field) is not None]
    without_value = [r for r in records if getattr(r, field) is None]

    with_value.sort(key=lambda r: getattr(r, field), reverse=descending)
    return with_value + without_value
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/dashboard/test_sorting.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/research/dashboard/sorting.py backend/tests/research/dashboard/test_sorting.py
git commit -m "feat(research-dashboard): add sort_records (display-only)"
```

---

## Task 3: `build_dashboard_table`

**Files:**
- Create: `backend/research/dashboard/table.py`
- Test: `backend/tests/research/dashboard/test_table.py`

**Interfaces:**
- Produces: `research.dashboard.table.build_dashboard_table(records: list[StrategyCatalogRecord]) -> pl.DataFrame` with columns exactly `["Strategy", "Category", "Hypothesis", "Market", "Timeframe", "Profit Factor", "Sharpe", "Expectancy", "Win Rate", "Max Drawdown", "Total Return", "Trades", "Fees", "Created At"]`. Task 6 (`cli.py`) calls this after filtering/sorting.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/dashboard/test_table.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from research.dashboard.table import build_dashboard_table
from research.models import StrategyCatalogRecord

_COLUMNS = [
    "Strategy", "Category", "Hypothesis", "Market", "Timeframe",
    "Profit Factor", "Sharpe", "Expectancy", "Win Rate", "Max Drawdown",
    "Total Return", "Trades", "Fees", "Created At",
]


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="trend_following",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=10,
        total_trades=8,
        win_rate=0.5,
        profit_factor=1.4,
        expectancy=5.0,
        sharpe_ratio=0.8,
        max_drawdown=0.1,
        total_return=4.2,
        total_fees=20.0,
        rejected_signals=2,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return StrategyCatalogRecord(**base)


def test_build_dashboard_table_returns_expected_columns_in_order() -> None:
    df = build_dashboard_table([_record()])

    assert df.columns == _COLUMNS


def test_build_dashboard_table_maps_values_correctly() -> None:
    record = _record()

    df = build_dashboard_table([record])

    row = df.row(0, named=True)
    assert row["Strategy"] == record.strategy_name
    assert row["Category"] == record.category
    assert row["Hypothesis"] == record.hypothesis
    assert row["Market"] == record.market
    assert row["Timeframe"] == record.timeframe
    assert row["Profit Factor"] == record.profit_factor
    assert row["Sharpe"] == record.sharpe_ratio
    assert row["Expectancy"] == record.expectancy
    assert row["Win Rate"] == record.win_rate
    assert row["Max Drawdown"] == record.max_drawdown
    assert row["Total Return"] == record.total_return
    assert row["Trades"] == record.total_trades
    assert row["Fees"] == record.total_fees


def test_build_dashboard_table_handles_empty_list() -> None:
    df = build_dashboard_table([])

    assert df.columns == _COLUMNS
    assert df.is_empty()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/dashboard/test_table.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.dashboard.table'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/dashboard/table.py`:

```python
from __future__ import annotations

import polars as pl

from research.models import StrategyCatalogRecord

_SCHEMA = {
    "Strategy": pl.Utf8,
    "Category": pl.Utf8,
    "Hypothesis": pl.Utf8,
    "Market": pl.Utf8,
    "Timeframe": pl.Utf8,
    "Profit Factor": pl.Float64,
    "Sharpe": pl.Float64,
    "Expectancy": pl.Float64,
    "Win Rate": pl.Float64,
    "Max Drawdown": pl.Float64,
    "Total Return": pl.Float64,
    "Trades": pl.Int64,
    "Fees": pl.Float64,
    "Created At": pl.Datetime,
}


def build_dashboard_table(records: list[StrategyCatalogRecord]) -> pl.DataFrame:
    rows = [
        {
            "Strategy": record.strategy_name,
            "Category": record.category,
            "Hypothesis": record.hypothesis,
            "Market": record.market,
            "Timeframe": record.timeframe,
            "Profit Factor": record.profit_factor,
            "Sharpe": record.sharpe_ratio,
            "Expectancy": record.expectancy,
            "Win Rate": record.win_rate,
            "Max Drawdown": record.max_drawdown,
            "Total Return": record.total_return,
            "Trades": record.total_trades,
            "Fees": record.total_fees,
            "Created At": record.created_at,
        }
        for record in records
    ]
    return pl.DataFrame(rows, schema=_SCHEMA)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/dashboard/test_table.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/research/dashboard/table.py backend/tests/research/dashboard/test_table.py
git commit -m "feat(research-dashboard): add build_dashboard_table"
```

---

## Task 4: `compute_summary_stats`

**Files:**
- Create: `backend/research/dashboard/stats.py`
- Test: `backend/tests/research/dashboard/test_stats.py`

**Interfaces:**
- Consumes: `research.dashboard.sorting.SORT_FIELDS` (Task 2).
- Produces: `research.dashboard.stats.SummaryStats` (frozen dataclass with fields `total_experiments: int, avg_profit_factor: float | None, avg_sharpe: float | None, avg_max_drawdown: float | None, best_experiment_metric: str | None, best_experiment: StrategyCatalogRecord | None`) and `research.dashboard.stats.compute_summary_stats(records: list[StrategyCatalogRecord], best_metric: str | None) -> SummaryStats`. Task 6 (`cli.py`) calls this with `best_metric=args.sort`.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/dashboard/test_stats.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research.dashboard.stats import compute_summary_stats
from research.models import StrategyCatalogRecord


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="trend_following",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=10,
        total_trades=8,
        win_rate=0.5,
        profit_factor=1.4,
        expectancy=5.0,
        sharpe_ratio=0.8,
        max_drawdown=0.1,
        total_return=4.2,
        total_fees=20.0,
        rejected_signals=2,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return StrategyCatalogRecord(**base)


def test_compute_summary_stats_counts_and_averages() -> None:
    records = [
        _record(experiment_id="a", profit_factor=1.0, sharpe_ratio=0.5, max_drawdown=0.1),
        _record(experiment_id="b", profit_factor=3.0, sharpe_ratio=1.5, max_drawdown=0.3),
    ]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.total_experiments == 2
    assert stats.avg_profit_factor == pytest.approx(2.0)
    assert stats.avg_sharpe == pytest.approx(1.0)
    assert stats.avg_max_drawdown == pytest.approx(0.2)


def test_compute_summary_stats_averages_skip_none_values() -> None:
    records = [
        _record(experiment_id="a", profit_factor=2.0),
        _record(experiment_id="b", profit_factor=None),
    ]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.avg_profit_factor == pytest.approx(2.0)


def test_compute_summary_stats_averages_are_none_when_all_null() -> None:
    records = [_record(profit_factor=None, sharpe_ratio=None, max_drawdown=None)]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.avg_profit_factor is None
    assert stats.avg_sharpe is None
    assert stats.avg_max_drawdown is None


def test_compute_summary_stats_best_experiment_is_none_without_explicit_metric() -> None:
    records = [_record(profit_factor=99.0)]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.best_experiment is None
    assert stats.best_experiment_metric is None


def test_compute_summary_stats_best_experiment_uses_given_metric() -> None:
    low = _record(experiment_id="a", profit_factor=1.0)
    high = _record(experiment_id="b", profit_factor=5.0)

    stats = compute_summary_stats([low, high], best_metric="profit_factor")

    assert stats.best_experiment.experiment_id == "b"
    assert stats.best_experiment_metric == "profit_factor"


def test_compute_summary_stats_best_experiment_none_when_metric_all_null() -> None:
    records = [_record(sharpe_ratio=None)]

    stats = compute_summary_stats(records, best_metric="sharpe")

    assert stats.best_experiment is None
    assert stats.best_experiment_metric is None


def test_compute_summary_stats_raises_on_unknown_best_metric() -> None:
    with pytest.raises(ValueError):
        compute_summary_stats([_record()], best_metric="not_a_metric")


def test_compute_summary_stats_handles_empty_records() -> None:
    stats = compute_summary_stats([], best_metric=None)

    assert stats.total_experiments == 0
    assert stats.avg_profit_factor is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/dashboard/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.dashboard.stats'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/dashboard/stats.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from research.dashboard.sorting import SORT_FIELDS
from research.models import StrategyCatalogRecord


@dataclass(frozen=True)
class SummaryStats:
    total_experiments: int
    avg_profit_factor: float | None
    avg_sharpe: float | None
    avg_max_drawdown: float | None
    best_experiment_metric: str | None
    best_experiment: StrategyCatalogRecord | None


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute_summary_stats(
    records: list[StrategyCatalogRecord],
    best_metric: str | None,
) -> SummaryStats:
    avg_profit_factor = _average([r.profit_factor for r in records if r.profit_factor is not None])
    avg_sharpe = _average([r.sharpe_ratio for r in records if r.sharpe_ratio is not None])
    avg_max_drawdown = _average([r.max_drawdown for r in records if r.max_drawdown is not None])

    best_experiment: StrategyCatalogRecord | None = None
    if best_metric is not None:
        if best_metric not in SORT_FIELDS:
            raise ValueError(f"unknown sort key: {best_metric!r}")
        field = SORT_FIELDS[best_metric]
        candidates = [r for r in records if getattr(r, field) is not None]
        if candidates:
            best_experiment = max(candidates, key=lambda r: getattr(r, field))

    return SummaryStats(
        total_experiments=len(records),
        avg_profit_factor=avg_profit_factor,
        avg_sharpe=avg_sharpe,
        avg_max_drawdown=avg_max_drawdown,
        best_experiment_metric=best_metric if best_experiment is not None else None,
        best_experiment=best_experiment,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/dashboard/test_stats.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/research/dashboard/stats.py backend/tests/research/dashboard/test_stats.py
git commit -m "feat(research-dashboard): add compute_summary_stats"
```

---

## Task 5: CSV/Markdown export

**Files:**
- Create: `backend/research/dashboard/export.py`
- Test: `backend/tests/research/dashboard/test_export.py`

**Interfaces:**
- Produces: `research.dashboard.export.export_table_csv(df: pl.DataFrame, path: Path) -> None` and `research.dashboard.export.export_table_markdown(df: pl.DataFrame, path: Path) -> None`. Task 6 (`cli.py`) calls both, optionally, on the already-built display table.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/dashboard/test_export.py`:

```python
from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from research.dashboard.export import export_table_csv, export_table_markdown


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Strategy": ["strat_a"],
            "Profit Factor": [1.4],
            "Sharpe": [None],
        }
    )


def test_export_table_csv_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"

    export_table_csv(_sample_df(), path)

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["Strategy"] == "strat_a"
    assert rows[0]["Profit Factor"] == "1.4"


def test_export_table_markdown_has_header_separator_and_row(tmp_path: Path) -> None:
    path = tmp_path / "table.md"

    export_table_markdown(_sample_df(), path)

    lines = path.read_text().splitlines()
    assert lines[0] == "| Strategy | Profit Factor | Sharpe |"
    assert lines[1] == "| --- | --- | --- |"
    assert lines[2] == "| strat_a | 1.4 | |"


def test_export_table_markdown_handles_empty_dataframe(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    df = pl.DataFrame(
        {"Strategy": [], "Profit Factor": []},
        schema={"Strategy": pl.Utf8, "Profit Factor": pl.Float64},
    )

    export_table_markdown(df, path)

    lines = path.read_text().splitlines()
    assert lines[0] == "| Strategy | Profit Factor |"
    assert lines[1] == "| --- | --- |"
    assert len(lines) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/dashboard/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.dashboard.export'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/dashboard/export.py`:

```python
from __future__ import annotations

from pathlib import Path

import polars as pl


def export_table_csv(df: pl.DataFrame, path: Path) -> None:
    df.write_csv(path)


def export_table_markdown(df: pl.DataFrame, path: Path) -> None:
    header = "| " + " | ".join(df.columns) + " |"
    separator = "| " + " | ".join("---" for _ in df.columns) + " |"
    lines = [header, separator]
    for row in df.iter_rows():
        cells = ["" if value is None else str(value) for value in row]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/dashboard/test_export.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/research/dashboard/export.py backend/tests/research/dashboard/test_export.py
git commit -m "feat(research-dashboard): add CSV/Markdown table export"
```

---

## Task 6: CLI + README

**Files:**
- Create: `backend/research/dashboard/cli.py`
- Create: `backend/research/dashboard/README.md`
- Test: `backend/tests/research/dashboard/test_cli.py`

**Interfaces:**
- Consumes: `research.catalog.load_catalog` (existing), `filter_records` (Task 1), `sort_records`/`SORT_FIELDS` (Task 2), `build_dashboard_table` (Task 3), `compute_summary_stats` (Task 4), `export_table_csv`/`export_table_markdown` (Task 5).
- Produces: `research.dashboard.cli.build_parser() -> argparse.ArgumentParser` and `research.dashboard.cli.main(argv: list[str] | None = None) -> int`. Nothing downstream depends on these — last module task.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/dashboard/test_cli.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.dashboard.cli import build_parser, main
from research.models import StrategyCatalogRecord


def _write_record(catalog_dir: Path, **overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id=overrides.get("experiment_id", "strat_a_20260101T000000_11111111"),
        strategy_name="strat_a",
        category="trend_following",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=10,
        total_trades=8,
        win_rate=0.5,
        profit_factor=1.4,
        expectancy=5.0,
        sharpe_ratio=0.8,
        max_drawdown=0.1,
        total_return=4.2,
        total_fees=20.0,
        rejected_signals=2,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    record = StrategyCatalogRecord(**base)
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / f"{record.experiment_id}.json").write_text(record.model_dump_json())
    return record


def test_build_parser_defaults() -> None:
    args = build_parser().parse_args([])

    assert args.category is None
    assert args.order == "desc"


def test_main_prints_table_and_stats(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir, experiment_id="a", strategy_name="strat_a", profit_factor=1.0)
    _write_record(catalog_dir, experiment_id="b", strategy_name="strat_b", profit_factor=3.0)

    exit_code = main(["--catalog-dir", str(catalog_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strat_a" in captured.out
    assert "strat_b" in captured.out
    assert "Total experiments: 2" in captured.out
    assert "Best experiment: N/A" in captured.out


def test_main_applies_filters(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir, experiment_id="a", strategy_name="strat_a", category="trend_following")
    _write_record(catalog_dir, experiment_id="b", strategy_name="strat_b", category="mean_reversion")

    exit_code = main(["--catalog-dir", str(catalog_dir), "--category", "trend"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strat_a" in captured.out
    assert "strat_b" not in captured.out


def test_main_sorts_and_reports_best_experiment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir, experiment_id="a", strategy_name="strat_a", profit_factor=1.0)
    _write_record(catalog_dir, experiment_id="b", strategy_name="strat_b", profit_factor=3.0)

    exit_code = main(["--catalog-dir", str(catalog_dir), "--sort", "profit_factor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Best experiment (profit_factor): strat_b" in captured.out


def test_main_exports_csv_and_markdown(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir)
    csv_path = tmp_path / "out.csv"
    md_path = tmp_path / "out.md"

    exit_code = main(
        [
            "--catalog-dir", str(catalog_dir),
            "--export-csv", str(csv_path),
            "--export-markdown", str(md_path),
        ]
    )

    assert exit_code == 0
    assert csv_path.exists()
    assert md_path.exists()


def test_main_returns_error_code_on_invalid_sort(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir)

    exit_code = main(["--catalog-dir", str(catalog_dir), "--sort", "not_a_metric"])

    assert exit_code == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/dashboard/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.dashboard.cli'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/dashboard/cli.py`:

```python
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research.catalog import load_catalog
from research.dashboard.export import export_table_csv, export_table_markdown
from research.dashboard.filters import filter_records
from research.dashboard.sorting import sort_records
from research.dashboard.stats import compute_summary_stats
from research.dashboard.table import build_dashboard_table

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[3] / "research" / "catalog"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.research.dashboard.cli")
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_CATALOG_DIR)
    parser.add_argument("--category", default=None)
    parser.add_argument("--market", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--sort", default=None)
    parser.add_argument("--order", choices=["asc", "desc"], default="desc")
    parser.add_argument("--export-csv", type=Path, default=None)
    parser.add_argument("--export-markdown", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    parser = build_parser()
    args = parser.parse_args(argv)

    records = load_catalog(args.catalog_dir)
    filtered = filter_records(records, category=args.category, market=args.market, timeframe=args.timeframe)

    try:
        ordered = sort_records(filtered, sort_key=args.sort, descending=(args.order != "asc"))
        stats = compute_summary_stats(filtered, best_metric=args.sort)
    except ValueError as error:
        logger.error("Invalid --sort value: %s", error)
        return 1

    table = build_dashboard_table(ordered)
    print(table)

    print("\nSummary statistics")
    print(f"  Total experiments: {stats.total_experiments}")
    print(f"  Avg profit factor: {stats.avg_profit_factor}")
    print(f"  Avg Sharpe: {stats.avg_sharpe}")
    print(f"  Avg max drawdown: {stats.avg_max_drawdown}")
    if stats.best_experiment is not None:
        print(
            f"  Best experiment ({stats.best_experiment_metric}): "
            f"{stats.best_experiment.strategy_name} ({stats.best_experiment.experiment_id})"
        )
    else:
        print("  Best experiment: N/A (no --sort given, or no experiment has that metric)")

    if args.export_csv is not None:
        export_table_csv(table, args.export_csv)
        logger.info("Exported CSV to %s", args.export_csv)
    if args.export_markdown is not None:
        export_table_markdown(table, args.export_markdown)
        logger.info("Exported Markdown to %s", args.export_markdown)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/dashboard/test_cli.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Write the README**

Create `backend/research/dashboard/README.md`:

```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add backend/research/dashboard/cli.py backend/research/dashboard/README.md backend/tests/research/dashboard/test_cli.py
git commit -m "feat(research-dashboard): add CLI entry point and README"
```

---

## Task 7: Demonstration — register historical runs and run the dashboard

**Files:**
- No new source files. Uses `research.catalog.register_strategy_result` (existing, unmodified) via a short one-off Python invocation, then `research.dashboard.cli.main` against the real `Trader_v2/research/catalog/` directory.

**Interfaces:**
- Consumes: `research.catalog.register_strategy_result` (existing), `report.builder.ReportSummary` (existing), `research.dashboard.cli.main` (Task 6).

- [ ] **Step 1: Confirm neither historical run is already registered**

Run: `ls "Trader_v2/research/catalog/"` (from repo root) — expect either the directory not to exist yet, or to contain no files whose `experiment_id` starts with `ema_trend_pullback_` or `donchian_breakout_`. This check exists specifically to avoid a duplicate registration if this task is ever re-run.

- [ ] **Step 2: Register the EMA Trend Pullback historical run**

From `backend/`, run a one-off interpreter invocation that reads
`reports/run_20260731T143348_de3fb080/summary.json`, reconstructs a
`ReportSummary`, and calls `register_strategy_result`:

```bash
.venv/Scripts/python.exe -c "
import json
from datetime import datetime
from pathlib import Path

from engine.models import BacktestConfig
from report.builder import GapWarning, ReportSummary
from research.catalog import register_strategy_result

run_dir = Path('../reports/run_20260731T143348_de3fb080')
data = json.loads((run_dir / 'summary.json').read_text())

summary = ReportSummary(
    symbol=data['symbol'],
    timeframe=data['timeframe'],
    exchange=data['exchange'],
    dataset_start=datetime.fromisoformat(data['dataset_start']),
    dataset_end=datetime.fromisoformat(data['dataset_end']),
    dataset_status=data['dataset_status'],
    gap_warnings=[GapWarning(start=datetime.fromisoformat(g['start']), end=datetime.fromisoformat(g['end']), severity=g['severity']) for g in data['gap_warnings']],
    config=BacktestConfig(**data['config']),
    num_signals=data['num_signals'],
    num_trades=data['num_trades'],
    num_rejected_signals=data['num_rejected_signals'],
    initial_equity=data['initial_equity'],
    final_equity=data['final_equity'],
    net_pnl=data['net_pnl'],
    return_pct=data['return_pct'],
    win_rate=data['win_rate'],
    profit_factor=data['profit_factor'],
    expectancy=data['expectancy'],
    sharpe_ratio=data['sharpe_ratio'],
    max_drawdown_pct=data['max_drawdown_pct'],
    max_consecutive_losses=data['max_consecutive_losses'],
    total_fees_paid=data['total_fees_paid'],
    exit_reason_counts=data['exit_reason_counts'],
)

record = register_strategy_result(
    summary=summary,
    strategy_name='ema_trend_pullback',
    category='trend_following',
    hypothesis='Price pulling back to the EMA20 within an EMA50>EMA200 uptrend (or the mirrored downtrend) resumes in the trend direction.',
    report_directory=run_dir,
    catalog_dir=Path('../research/catalog'),
)
print('registered', record.experiment_id)
"
```

Expected: prints `registered ema_trend_pullback_<timestamp>_<uuid8>` and creates exactly one new file under `Trader_v2/research/catalog/`.

- [ ] **Step 3: Register the Donchian Breakout historical run**

Repeat Step 2's invocation with `run_dir = Path('../reports/run_20260731T174825_bc6cd6d5')`, `strategy_name='donchian_breakout'`, `category='trend_following'`, and `hypothesis='A close beyond the prior 20-period high/low channel continues in the breakout direction.'`.

Expected: prints `registered donchian_breakout_<timestamp>_<uuid8>` and creates exactly one more new file under `Trader_v2/research/catalog/` (two total).

- [ ] **Step 4: Run the dashboard against the real catalog**

From `backend/`, run each of:

```bash
.venv/Scripts/python.exe -m research.dashboard.cli
.venv/Scripts/python.exe -m research.dashboard.cli --category trend
.venv/Scripts/python.exe -m research.dashboard.cli --sort profit_factor
.venv/Scripts/python.exe -m research.dashboard.cli --market BTCUSDT --timeframe 15m --sort sharpe --order asc
.venv/Scripts/python.exe -m research.dashboard.cli --export-csv /tmp_or_scratch/dashboard.csv --export-markdown /tmp_or_scratch/dashboard.md
```

Expected: each prints a two-row table (both EMA Trend Pullback and
Donchian Breakout) except the filtered ones, which still show both
(both are `trend_following` / `BTC/USDT` / `15m`); the `--sort` runs show
a populated `Best experiment (<metric>): ...` line instead of `N/A`; the
export run creates both output files.

- [ ] **Step 5: Commit the two new catalog record files**

```bash
git add "Trader_v2/research/catalog/"
git commit -m "chore(research): register historical EMA Trend Pullback and Donchian Breakout runs"
```

(Run from repo root; adjust the path if the working directory differs — this commits exactly the two new JSON files created in Steps 2–3, nothing else.)

---

## Final Verification

- [ ] Run the full dashboard suite: `pytest tests/research/dashboard/ -v` — expect 32 passed.
- [ ] Run the full backend suite to confirm no other module was touched or broken: `pytest -v`.
- [ ] Confirm the diff is scoped to `backend/research/dashboard/`, `backend/tests/research/dashboard/`, and the two new catalog record files: `git status`.

# Strategy Research Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `backend/research/` module that records immutable, append-only experiment results (`StrategyCatalogRecord`) from completed backtests and produces a side-by-side comparison table, without modifying any existing module.

**Architecture:** Four small, single-responsibility files — `models.py` (frozen Pydantic record), `catalog.py` (write/read, one JSON file per experiment), `comparison.py` (pure `pl.DataFrame` builder), `export.py` (CSV/JSON dump of the full catalog) — built in that dependency order, each with its own test file, strict TDD (failing test committed to red before any implementation code is written).

**Tech Stack:** Python 3.12, Pydantic 2.9+ (frozen models), Polars (comparison table only), stdlib `csv`/`json` for export, pytest.

## Global Constraints

- Do not modify any file under `data/`, `engine/`, `risk/`, `analytics/`, `report/`, `runner/`, `diagnostics/`, `strategy/`, or `strategies/` — `research/` only ever *imports* `report.builder.ReportSummary` as a read-only type.
- `report/` must never import anything from `research/` — dependency direction is one-way (`report -> research`).
- Every catalog record is one immutable JSON file; `register_strategy_result()` must never open an existing record file for writing.
- Every experiment record carries a unique `experiment_id` (`f"{strategy_name}_{created_at:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"`).
- `compare_strategies()` output is ordered only by `created_at` (or `strategy_name`) — never by any performance metric.
- Pure Python, type hints on every function signature, `logging` (never `print`) for any runtime diagnostics, one unit test file per module.
- Reference design: `docs/superpowers/specs/2026-08-01-strategy-research-database-design.md`.

---

## Task 1: Package scaffolding + `StrategyCatalogRecord` model

**Files:**
- Modify: `backend/pyproject.toml` (add `"research*"` to `[tool.setuptools.packages.find].include`)
- Create: `backend/research/__init__.py` (empty)
- Create: `backend/research/models.py`
- Create: `backend/tests/research/__init__.py` (empty)
- Test: `backend/tests/research/test_models.py`

**Interfaces:**
- Produces: `research.models.StrategyCatalogRecord` — a frozen `pydantic.BaseModel` with fields `experiment_id: str, strategy_name: str, category: str, hypothesis: str, market: str, timeframe: str, start_date: datetime, end_date: datetime, initial_capital: float, total_signals: int, total_trades: int, win_rate: float | None, profit_factor: float | None, expectancy: float | None, sharpe_ratio: float | None, max_drawdown: float | None, total_return: float, total_fees: float, rejected_signals: int, report_directory: str, created_at: datetime`. Later tasks import this type and construct it with all 21 keyword arguments.

- [ ] **Step 1: Register the new package with setuptools**

Edit `backend/pyproject.toml` line 22 from:

```toml
include = ["data*", "risk*", "engine*", "analytics*", "strategy*", "report*", "runner*", "strategies*"]
```

to:

```toml
include = ["data*", "risk*", "engine*", "analytics*", "strategy*", "report*", "runner*", "strategies*", "research*"]
```

- [ ] **Step 2: Create empty package `__init__.py` files**

Create `backend/research/__init__.py` (empty file) and `backend/tests/research/__init__.py` (empty file), matching the pattern already used by every other package (e.g. `backend/strategies/__init__.py`).

- [ ] **Step 3: Write the failing test file**

Create `backend/tests/research/test_models.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from research.models import StrategyCatalogRecord


def _sample_kwargs() -> dict:
    return dict(
        experiment_id="donchian_breakout_20260801T120000_abcd1234",
        strategy_name="donchian_breakout",
        category="breakout",
        hypothesis="Closes beyond a 20-period channel continue in that direction.",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=42,
        total_trades=38,
        win_rate=0.45,
        profit_factor=1.3,
        expectancy=12.5,
        sharpe_ratio=0.9,
        max_drawdown=0.12,
        total_return=8.4,
        total_fees=120.0,
        rejected_signals=4,
        report_directory="reports/run_20260801T120000_abcd1234",
        created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_strategy_catalog_record_accepts_all_fields() -> None:
    record = StrategyCatalogRecord(**_sample_kwargs())

    assert record.strategy_name == "donchian_breakout"
    assert record.experiment_id == "donchian_breakout_20260801T120000_abcd1234"


def test_strategy_catalog_record_is_frozen() -> None:
    record = StrategyCatalogRecord(**_sample_kwargs())

    with pytest.raises(ValidationError):
        record.strategy_name = "changed"


def test_strategy_catalog_record_accepts_none_metrics() -> None:
    kwargs = _sample_kwargs()
    kwargs.update(win_rate=None, profit_factor=None, expectancy=None, sharpe_ratio=None, max_drawdown=None)

    record = StrategyCatalogRecord(**kwargs)

    assert record.win_rate is None
    assert record.profit_factor is None


def test_strategy_catalog_record_requires_all_fields() -> None:
    kwargs = _sample_kwargs()
    del kwargs["strategy_name"]

    with pytest.raises(ValidationError):
        StrategyCatalogRecord(**kwargs)
```

- [ ] **Step 4: Run the test to verify it fails**

Run (from `backend/`): `pytest tests/research/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research'` (or `models`) since neither `research/__init__.py`'s sibling `models.py` nor the editable install mapping exist yet.

- [ ] **Step 5: Register the package with the editable install**

Run (from `backend/`, using the project's venv): `.venv/Scripts/python.exe -m pip install -e . --no-deps -q`

This regenerates `.venv/Lib/site-packages/__editable___trader_v2_backend_*_finder.py`'s `MAPPING` dict so `import research` resolves — required because this project uses a PEP 660 editable install with an explicit package mapping (confirmed by inspecting the existing finder file), not a live `sys.path` scan, so newly-added packages are invisible until reinstalled.

- [ ] **Step 6: Run the test again to confirm the import now resolves but the module is still missing**

Run: `pytest tests/research/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.models'`

- [ ] **Step 7: Write the minimal implementation**

Create `backend/research/models.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrategyCatalogRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str
    strategy_name: str
    category: str
    hypothesis: str
    market: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    total_signals: int
    total_trades: int
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_return: float
    total_fees: float
    rejected_signals: int
    report_directory: str
    created_at: datetime
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/research/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/research/__init__.py backend/research/models.py backend/tests/research/__init__.py backend/tests/research/test_models.py
git commit -m "feat(research): add frozen StrategyCatalogRecord model"
```

---

## Task 2: Append-only catalog storage (`register_strategy_result`, `load_catalog`)

**Files:**
- Create: `backend/research/catalog.py`
- Test: `backend/tests/research/test_catalog.py`

**Interfaces:**
- Consumes: `research.models.StrategyCatalogRecord` (Task 1); `report.builder.ReportSummary` (existing, read-only — fields used: `symbol, timeframe, dataset_start, dataset_end, config.initial_capital, num_signals, num_trades, num_rejected_signals, win_rate, profit_factor, expectancy, sharpe_ratio, max_drawdown_pct, return_pct, total_fees_paid`); `engine.models.BacktestConfig` (existing, only in the test file to build a sample `ReportSummary`).
- Produces: `research.catalog.register_strategy_result(summary: ReportSummary, strategy_name: str, category: str, hypothesis: str, report_directory: Path, catalog_dir: Path) -> StrategyCatalogRecord` and `research.catalog.load_catalog(catalog_dir: Path) -> list[StrategyCatalogRecord]`. Task 3 and Task 4 both take `list[StrategyCatalogRecord]` as produced by `load_catalog`.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/test_catalog.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.models import BacktestConfig
from report.builder import ReportSummary
from research.catalog import load_catalog, register_strategy_result
from research.models import StrategyCatalogRecord


def _sample_summary() -> ReportSummary:
    return ReportSummary(
        symbol="BTC/USDT",
        timeframe="15m",
        exchange="binance",
        dataset_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        dataset_end=datetime(2024, 6, 1, tzinfo=timezone.utc),
        dataset_status="complete",
        gap_warnings=[],
        config=BacktestConfig(
            initial_capital=10000.0,
            leverage=1.0,
            risk_per_trade_pct=1.0,
            fee_pct=0.04,
            slippage_pct=0.01,
        ),
        num_signals=42,
        num_trades=38,
        num_rejected_signals=4,
        initial_equity=10000.0,
        final_equity=10840.0,
        net_pnl=840.0,
        return_pct=8.4,
        win_rate=0.45,
        profit_factor=1.3,
        expectancy=12.5,
        sharpe_ratio=0.9,
        max_drawdown_pct=0.12,
        max_consecutive_losses=3,
        total_fees_paid=120.0,
        exit_reason_counts={"take_profit": 20, "stop_loss": 18},
    )


def _sample_record(catalog_dir: Path, **overrides) -> StrategyCatalogRecord:
    kwargs = dict(
        summary=_sample_summary(),
        strategy_name="donchian_breakout",
        category="breakout",
        hypothesis="Closes beyond a 20-period channel continue in that direction.",
        report_directory=Path("reports/run_a"),
        catalog_dir=catalog_dir,
    )
    kwargs.update(overrides)
    return register_strategy_result(**kwargs)


def test_register_strategy_result_writes_one_new_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"

    record = _sample_record(catalog_dir)

    files = list(catalog_dir.glob("*.json"))
    assert len(files) == 1
    assert files[0].stem == record.experiment_id


def test_register_strategy_result_maps_report_summary_fields(tmp_path: Path) -> None:
    summary = _sample_summary()

    record = _sample_record(tmp_path / "catalog", summary=summary)

    assert record.market == summary.symbol
    assert record.timeframe == summary.timeframe
    assert record.start_date == summary.dataset_start
    assert record.end_date == summary.dataset_end
    assert record.initial_capital == summary.config.initial_capital
    assert record.total_signals == summary.num_signals
    assert record.total_trades == summary.num_trades
    assert record.rejected_signals == summary.num_rejected_signals
    assert record.win_rate == summary.win_rate
    assert record.profit_factor == summary.profit_factor
    assert record.expectancy == summary.expectancy
    assert record.sharpe_ratio == summary.sharpe_ratio
    assert record.max_drawdown == summary.max_drawdown_pct
    assert record.total_return == summary.return_pct
    assert record.total_fees == summary.total_fees_paid
    assert record.report_directory == "reports/run_a"


def test_register_strategy_result_never_touches_previous_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    first = _sample_record(catalog_dir, hypothesis="First run.")
    first_path = catalog_dir / f"{first.experiment_id}.json"
    first_content_before = first_path.read_text()

    _sample_record(catalog_dir, hypothesis="Second run.")

    assert first_path.read_text() == first_content_before
    assert len(list(catalog_dir.glob("*.json"))) == 2


def test_register_strategy_result_twice_produces_distinct_experiment_ids(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"

    first = _sample_record(catalog_dir, hypothesis="First run.")
    second = _sample_record(catalog_dir, hypothesis="Second run.")

    assert first.experiment_id != second.experiment_id


def test_load_catalog_round_trips_a_registered_record(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    registered = _sample_record(catalog_dir)

    loaded = load_catalog(catalog_dir)

    assert loaded == [registered]


def test_load_catalog_orders_by_created_at(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir(parents=True)

    older = StrategyCatalogRecord(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="breakout",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=1,
        total_trades=1,
        win_rate=None,
        profit_factor=None,
        expectancy=None,
        sharpe_ratio=None,
        max_drawdown=None,
        total_return=1.0,
        total_fees=1.0,
        rejected_signals=0,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = older.model_copy(
        update={
            "experiment_id": "strat_b_20260201T000000_22222222",
            "strategy_name": "strat_b",
            "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        }
    )

    (catalog_dir / f"{newer.experiment_id}.json").write_text(newer.model_dump_json())
    (catalog_dir / f"{older.experiment_id}.json").write_text(older.model_dump_json())

    loaded = load_catalog(catalog_dir)

    assert [r.experiment_id for r in loaded] == [older.experiment_id, newer.experiment_id]


def test_load_catalog_raises_on_malformed_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "broken.json").write_text("{not valid json")

    with pytest.raises(ValueError):
        load_catalog(catalog_dir)


def test_load_catalog_returns_empty_list_for_missing_directory(tmp_path: Path) -> None:
    assert load_catalog(tmp_path / "does_not_exist") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.catalog'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/catalog.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from report.builder import ReportSummary

from research.models import StrategyCatalogRecord

logger = logging.getLogger(__name__)


def _build_experiment_id(strategy_name: str, created_at: datetime) -> str:
    return f"{strategy_name}_{created_at:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"


def register_strategy_result(
    summary: ReportSummary,
    strategy_name: str,
    category: str,
    hypothesis: str,
    report_directory: Path,
    catalog_dir: Path,
) -> StrategyCatalogRecord:
    created_at = datetime.now(timezone.utc)
    experiment_id = _build_experiment_id(strategy_name, created_at)

    record = StrategyCatalogRecord(
        experiment_id=experiment_id,
        strategy_name=strategy_name,
        category=category,
        hypothesis=hypothesis,
        market=summary.symbol,
        timeframe=summary.timeframe,
        start_date=summary.dataset_start,
        end_date=summary.dataset_end,
        initial_capital=summary.config.initial_capital,
        total_signals=summary.num_signals,
        total_trades=summary.num_trades,
        win_rate=summary.win_rate,
        profit_factor=summary.profit_factor,
        expectancy=summary.expectancy,
        sharpe_ratio=summary.sharpe_ratio,
        max_drawdown=summary.max_drawdown_pct,
        total_return=summary.return_pct,
        total_fees=summary.total_fees_paid,
        rejected_signals=summary.num_rejected_signals,
        report_directory=str(report_directory),
        created_at=created_at,
    )

    catalog_dir.mkdir(parents=True, exist_ok=True)
    record_path = catalog_dir / f"{experiment_id}.json"
    if record_path.exists():
        raise FileExistsError(f"catalog record already exists: {record_path}")

    record_path.write_text(record.model_dump_json(indent=2))
    logger.info("registered strategy result %s -> %s", strategy_name, record_path)
    return record


def load_catalog(catalog_dir: Path) -> list[StrategyCatalogRecord]:
    records: list[StrategyCatalogRecord] = []
    for path in sorted(catalog_dir.glob("*.json")):
        try:
            records.append(StrategyCatalogRecord.model_validate_json(path.read_text()))
        except Exception as exc:
            raise ValueError(f"failed to parse catalog record {path}: {exc}") from exc

    records.sort(key=lambda record: record.created_at)
    return records
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/test_catalog.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/research/catalog.py backend/tests/research/test_catalog.py
git commit -m "feat(research): add append-only register_strategy_result and load_catalog"
```

---

## Task 3: Comparison table (`compare_strategies`)

**Files:**
- Create: `backend/research/comparison.py`
- Test: `backend/tests/research/test_comparison.py`

**Interfaces:**
- Consumes: `research.models.StrategyCatalogRecord` (Task 1).
- Produces: `research.comparison.compare_strategies(records: list[StrategyCatalogRecord]) -> pl.DataFrame` with columns exactly `["strategy_name", "category", "profit_factor", "sharpe_ratio", "expectancy", "max_drawdown", "total_trades", "total_return"]`, ordered by `created_at`.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/test_comparison.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from research.comparison import compare_strategies
from research.models import StrategyCatalogRecord

_COLUMNS = [
    "strategy_name",
    "category",
    "profit_factor",
    "sharpe_ratio",
    "expectancy",
    "max_drawdown",
    "total_trades",
    "total_return",
]


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="breakout",
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


def test_compare_strategies_returns_expected_columns_in_order() -> None:
    df = compare_strategies([_record()])

    assert df.columns == _COLUMNS


def test_compare_strategies_orders_by_created_at_not_performance() -> None:
    better_but_older = _record(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        profit_factor=5.0,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    worse_but_newer = _record(
        experiment_id="strat_b_20260201T000000_22222222",
        strategy_name="strat_b",
        profit_factor=1.0,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    df = compare_strategies([worse_but_newer, better_but_older])

    assert df["strategy_name"].to_list() == ["strat_a", "strat_b"]


def test_compare_strategies_preserves_none_metrics() -> None:
    record = _record(profit_factor=None, sharpe_ratio=None, expectancy=None, max_drawdown=None)

    df = compare_strategies([record])

    assert df["profit_factor"].to_list() == [None]
    assert df["sharpe_ratio"].to_list() == [None]
    assert df["expectancy"].to_list() == [None]
    assert df["max_drawdown"].to_list() == [None]


def test_compare_strategies_handles_empty_list() -> None:
    df = compare_strategies([])

    assert df.columns == _COLUMNS
    assert df.is_empty()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/test_comparison.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.comparison'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/comparison.py`:

```python
from __future__ import annotations

import polars as pl

from research.models import StrategyCatalogRecord

_SCHEMA = {
    "strategy_name": pl.Utf8,
    "category": pl.Utf8,
    "profit_factor": pl.Float64,
    "sharpe_ratio": pl.Float64,
    "expectancy": pl.Float64,
    "max_drawdown": pl.Float64,
    "total_trades": pl.Int64,
    "total_return": pl.Float64,
}


def compare_strategies(records: list[StrategyCatalogRecord]) -> pl.DataFrame:
    ordered = sorted(records, key=lambda record: record.created_at)
    rows = [
        {
            "strategy_name": record.strategy_name,
            "category": record.category,
            "profit_factor": record.profit_factor,
            "sharpe_ratio": record.sharpe_ratio,
            "expectancy": record.expectancy,
            "max_drawdown": record.max_drawdown,
            "total_trades": record.total_trades,
            "total_return": record.total_return,
        }
        for record in ordered
    ]
    return pl.DataFrame(rows, schema=_SCHEMA)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/test_comparison.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/research/comparison.py backend/tests/research/test_comparison.py
git commit -m "feat(research): add compare_strategies side-by-side table builder"
```

---

## Task 4: Catalog export (CSV/JSON) + README

**Files:**
- Create: `backend/research/export.py`
- Create: `backend/research/README.md`
- Test: `backend/tests/research/test_export.py`

**Interfaces:**
- Consumes: `research.models.StrategyCatalogRecord` (Task 1).
- Produces: `research.export.export_catalog_csv(records: list[StrategyCatalogRecord], path: Path) -> None` and `research.export.export_catalog_json(records: list[StrategyCatalogRecord], path: Path) -> None`. Nothing downstream depends on these — this is the last task.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/research/test_export.py`:

```python
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from research.export import export_catalog_csv, export_catalog_json
from research.models import StrategyCatalogRecord


def _record() -> StrategyCatalogRecord:
    return StrategyCatalogRecord(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="breakout",
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


def test_export_catalog_csv_writes_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"

    export_catalog_csv([_record()], path)

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["experiment_id"] == "strat_a_20260101T000000_11111111"
    assert rows[0]["strategy_name"] == "strat_a"
    assert set(rows[0].keys()) == set(StrategyCatalogRecord.model_fields.keys())


def test_export_catalog_json_writes_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"

    export_catalog_json([_record()], path)

    payload = json.loads(path.read_text())
    assert len(payload) == 1
    assert payload[0]["experiment_id"] == "strat_a_20260101T000000_11111111"
    assert set(payload[0].keys()) == set(StrategyCatalogRecord.model_fields.keys())


def test_export_catalog_json_overwrites_previous_export_file(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    export_catalog_json([_record()], path)

    export_catalog_json([], path)

    assert json.loads(path.read_text()) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/research/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.export'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/research/export.py`:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path

from research.models import StrategyCatalogRecord

_FIELDS = list(StrategyCatalogRecord.model_fields.keys())


def export_catalog_csv(records: list[StrategyCatalogRecord], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.model_dump(mode="json"))


def export_catalog_json(records: list[StrategyCatalogRecord], path: Path) -> None:
    payload = [record.model_dump(mode="json") for record in records]
    path.write_text(json.dumps(payload, indent=2))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/research/test_export.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Write the README**

Create `backend/research/README.md`:

```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add backend/research/export.py backend/research/README.md backend/tests/research/test_export.py
git commit -m "feat(research): add catalog CSV/JSON export and README"
```

---

## Final Verification

- [ ] Run the full research suite: `pytest tests/research/ -v` — expect 20 passed.
- [ ] Run the full backend suite to confirm no other module was touched or broken: `pytest -v`.
- [ ] Confirm no diff outside `backend/research/`, `backend/tests/research/`, and the one `include` line in `backend/pyproject.toml`: `git diff --stat main...HEAD` (or `git status`).

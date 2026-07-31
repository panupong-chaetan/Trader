# Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Trader v2 Data Pipeline module — download OHLCV from Binance Spot via CCXT, validate it (time order, duplicates, missing candles), persist it to Parquet with a JSON metadata sidecar, and support incremental updates — exactly as specified in `docs/superpowers/specs/2026-07-31-data-pipeline-design.md`.

**Architecture:** Flat, function-oriented Python modules under `backend/data/` — `config` → `client` / `validator` / `storage` → `pipeline` → `cli`. Each module has one responsibility, communicates through plain functions/dataclasses/Pydantic models, and is unit-tested with fake/mocked CCXT fetchers (no live network calls anywhere in the test suite).

**Tech Stack:** Python 3.12, Polars, Pydantic v2, CCXT, pytest. No FastAPI or Supabase in this milestone.

## Global Constraints

- Python 3.12; every function has type hints.
- Use the `logging` module — never `print()`.
- No look-ahead bias / no future data: the pipeline never reads or writes data beyond `config.end`, and validation always completes before data is persisted.
- One file = one responsibility; do not combine validation, storage, and orchestration logic into a single file.
- Every significant module gets a README (see Task 9).
- This milestone does **not** touch Supabase or the REST API — CLI only.
- **Git is not initialized in `Trader_v2` yet, and must not be initialized during this plan.** Do not run `git init` or `git commit`. Replace the template's "Commit" step with a "Checkpoint" step (re-run the full test file, confirm green) at the end of each task.
- Storage paths use the symbol with `/` stripped (`BTC/USDT` → `BTCUSDT`); metadata keeps the original `symbol` string.
- Metadata sidecar filename is exactly `{timeframe}.metadata.json`.
- Gap thresholds: small = `missing_candles <= small_gap_max` (default 5), medium = `small_gap_max < missing_candles <= medium_gap_max` (default 20), large = `missing_candles > medium_gap_max`. Large gaps abort the run with no write; small/medium gaps retry `config.retry_count` times then get recorded with their severity in metadata `gaps[]`, and the dataset is marked `incomplete`. The Data Pipeline never decides backtest eligibility — it only reports `status` and per-gap `severity`.

All file paths below are relative to `Trader_v2/`.

---

### Task 1: Project scaffold and `DataIntegrityError`

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/data/__init__.py`
- Create: `backend/data/exceptions.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/data/__init__.py`
- Test: `backend/tests/data/test_exceptions.py`

**Interfaces:**
- Produces: `data.exceptions.DataIntegrityError(message: str, *, start: str | None = None, end: str | None = None)` — subclass of `Exception`, with `.start` and `.end` attributes. Used by every later module to signal unrecoverable validation failures.

- [ ] **Step 1: Create the project scaffold**

Create `backend/pyproject.toml`:

```toml
[project]
name = "trader-v2-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "polars>=1.9",
    "numpy>=2.1",
    "ccxt>=4.4",
    "pydantic>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.3"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["data*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create empty files `backend/data/__init__.py`, `backend/tests/__init__.py`, `backend/tests/data/__init__.py`.

- [ ] **Step 2: Install the package in editable mode**

Run (from `backend/`): `pip install -e ".[dev]"`
Expected: install succeeds, `data` package is importable.

- [ ] **Step 3: Write the failing test**

`backend/tests/data/test_exceptions.py`:

```python
from data.exceptions import DataIntegrityError


def test_data_integrity_error_carries_range_and_message() -> None:
    error = DataIntegrityError(
        "large gap detected",
        start="2024-01-01T00:00:00+00:00",
        end="2024-01-02T00:00:00+00:00",
    )

    assert str(error) == "large gap detected"
    assert error.start == "2024-01-01T00:00:00+00:00"
    assert error.end == "2024-01-02T00:00:00+00:00"


def test_data_integrity_error_defaults_range_to_none() -> None:
    error = DataIntegrityError("conflicting duplicate rows")

    assert error.start is None
    assert error.end is None
```

- [ ] **Step 4: Run the test to verify it fails**

Run (from `backend/`): `pytest tests/data/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.exceptions'`

- [ ] **Step 5: Implement `DataIntegrityError`**

`backend/data/exceptions.py`:

```python
from __future__ import annotations


class DataIntegrityError(Exception):
    """Raised when OHLCV data fails validation and cannot be safely persisted."""

    def __init__(
        self,
        message: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        super().__init__(message)
        self.start = start
        self.end = end
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/data/test_exceptions.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Checkpoint**

Re-run `pytest tests/data -v` from `backend/` and confirm all tests pass. Do not run any git commands.

---

### Task 2: `DownloadConfig`

**Files:**
- Create: `backend/data/config.py`
- Test: `backend/tests/data/test_config.py`

**Interfaces:**
- Consumes: nothing from other `data` modules.
- Produces: `data.config.DownloadConfig` (Pydantic `BaseModel`) with fields `exchange: str`, `symbol: str`, `timeframe: str`, `start: datetime`, `end: datetime | None = None`, `small_gap_max: int = 5`, `medium_gap_max: int = 20`, `retry_count: int = 1`, and a computed property `symbol_slug: str`. Raises `pydantic.ValidationError` on: `end <= start`, `medium_gap_max <= small_gap_max`, or any of `small_gap_max`/`medium_gap_max`/`retry_count` `< 1`. Used by every later module as the single configuration object.

- [ ] **Step 1: Write the failing tests**

`backend/tests/data/test_config.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data.config import DownloadConfig


def _base_kwargs() -> dict:
    return {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "start": datetime(2020, 1, 1, tzinfo=timezone.utc),
    }


def test_download_config_accepts_valid_input() -> None:
    config = DownloadConfig(**_base_kwargs())

    assert config.exchange == "binance"
    assert config.small_gap_max == 5
    assert config.medium_gap_max == 20
    assert config.retry_count == 1


def test_download_config_symbol_slug_strips_separator() -> None:
    config = DownloadConfig(**_base_kwargs())

    assert config.symbol_slug == "BTCUSDT"


def test_download_config_rejects_end_before_start() -> None:
    kwargs = _base_kwargs()
    kwargs["end"] = datetime(2019, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        DownloadConfig(**kwargs)


def test_download_config_rejects_medium_not_greater_than_small() -> None:
    kwargs = _base_kwargs()
    kwargs["small_gap_max"] = 10
    kwargs["medium_gap_max"] = 10

    with pytest.raises(ValidationError):
        DownloadConfig(**kwargs)


def test_download_config_rejects_non_positive_retry_count() -> None:
    kwargs = _base_kwargs()
    kwargs["retry_count"] = 0

    with pytest.raises(ValidationError):
        DownloadConfig(**kwargs)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.config'`

- [ ] **Step 3: Implement `DownloadConfig`**

`backend/data/config.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator


class DownloadConfig(BaseModel):
    exchange: str
    symbol: str
    timeframe: str
    start: datetime
    end: datetime | None = None
    small_gap_max: int = 5
    medium_gap_max: int = 20
    retry_count: int = 1

    @field_validator("small_gap_max", "medium_gap_max", "retry_count")
    @classmethod
    def _must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> "DownloadConfig":
        if self.medium_gap_max <= self.small_gap_max:
            raise ValueError("medium_gap_max must be greater than small_gap_max")
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be after start")
        return self

    @property
    def symbol_slug(self) -> str:
        return self.symbol.replace("/", "")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_config.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Checkpoint**

Re-run `pytest tests/data -v` and confirm all tests (Task 1 + Task 2) pass. Do not run any git commands.

---

### Task 3: Validator — sorting and duplicate handling

**Files:**
- Create: `backend/data/validator.py`
- Test: `backend/tests/data/test_validator.py`

**Interfaces:**
- Consumes: `data.exceptions.DataIntegrityError` (Task 1).
- Produces: `data.validator.sort_by_timestamp(df: pl.DataFrame) -> pl.DataFrame` and `data.validator.deduplicate(df: pl.DataFrame) -> pl.DataFrame`. Both operate on a Polars DataFrame with columns `timestamp` (`pl.Datetime`, UTC), `open`, `high`, `low`, `close`, `volume` (all `pl.Float64`). `deduplicate` raises `DataIntegrityError` on conflicting-OHLCV duplicates. Task 4 adds gap-detection functions to this same file; Task 6/7 rely on this exact column schema.

- [ ] **Step 1: Write the failing tests**

`backend/tests/data/test_validator.py`:

```python
from datetime import datetime, timezone

import polars as pl
import pytest

from data.exceptions import DataIntegrityError
from data.validator import deduplicate, sort_by_timestamp


def _row(ts: datetime, close: float = 100.0) -> dict:
    return {
        "timestamp": ts,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def test_sort_by_timestamp_orders_ascending() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t1), _row(t0)])

    sorted_df = sort_by_timestamp(df)

    assert sorted_df["timestamp"].to_list() == [t0, t1]


def test_deduplicate_drops_identical_duplicate_rows() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t0), _row(t0)])

    result = deduplicate(df)

    assert result.height == 1


def test_deduplicate_raises_on_conflicting_duplicate() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t0, close=100.0), _row(t0, close=101.0)])

    with pytest.raises(DataIntegrityError):
        deduplicate(df)


def test_deduplicate_leaves_unique_rows_untouched() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    df = pl.DataFrame([_row(t0), _row(t1)])

    result = deduplicate(df)

    assert result.height == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_validator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.validator'`

- [ ] **Step 3: Implement sorting and deduplication**

`backend/data/validator.py`:

```python
from __future__ import annotations

import logging

import polars as pl

from data.exceptions import DataIntegrityError

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def sort_by_timestamp(df: pl.DataFrame) -> pl.DataFrame:
    return df.sort("timestamp")


def deduplicate(df: pl.DataFrame) -> pl.DataFrame:
    duplicate_timestamps = (
        df.group_by("timestamp")
        .agg(pl.len().alias("count"))
        .filter(pl.col("count") > 1)
        .get_column("timestamp")
    )

    if duplicate_timestamps.is_empty():
        return df

    for timestamp in duplicate_timestamps:
        rows = df.filter(pl.col("timestamp") == timestamp)
        distinct_rows = rows.select(list(OHLCV_COLUMNS)).unique()
        if distinct_rows.height > 1:
            raise DataIntegrityError(
                f"Conflicting OHLCV values for duplicate timestamp {timestamp}",
                start=str(timestamp),
                end=str(timestamp),
            )
        logger.warning(
            "Dropping %d identical duplicate rows at timestamp %s",
            rows.height - 1,
            timestamp,
        )

    return df.unique(subset=["timestamp"], keep="first").sort("timestamp")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_validator.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Checkpoint**

Re-run `pytest tests/data -v` and confirm all tests pass. Do not run any git commands.

---

### Task 4: Validator — gap detection and classification

**Files:**
- Modify: `backend/data/validator.py` (append)
- Modify: `backend/tests/data/test_validator.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces (appended to `data.validator`): `timeframe_to_timedelta(timeframe: str) -> timedelta`; `@dataclass(frozen=True) class Gap: start: datetime; end: datetime; missing_candles: int; severity: str`; `classify_gap(missing_candles: int, small_gap_max: int, medium_gap_max: int) -> str` (returns `"small" | "medium" | "large"`); `find_gaps(df: pl.DataFrame, timeframe: str, small_gap_max: int, medium_gap_max: int) -> list[Gap]`. `Gap`, `find_gaps`, and `timeframe_to_timedelta` are consumed directly by Task 5 (storage), Task 6 (client), and Task 7 (pipeline).

- [ ] **Step 1: Write the failing tests (append to the existing file)**

Append to `backend/tests/data/test_validator.py`:

```python
from datetime import timedelta

from data.validator import classify_gap, find_gaps, timeframe_to_timedelta


def _candles(start: datetime, count: int, interval: timedelta, skip: set[int] | None = None) -> pl.DataFrame:
    skip = skip or set()
    rows = [
        _row(start + i * interval)
        for i in range(count)
        if i not in skip
    ]
    return pl.DataFrame(rows)


def test_timeframe_to_timedelta_parses_minutes_hours_days() -> None:
    assert timeframe_to_timedelta("15m") == timedelta(minutes=15)
    assert timeframe_to_timedelta("1h") == timedelta(hours=1)
    assert timeframe_to_timedelta("1d") == timedelta(days=1)


def test_classify_gap_boundaries() -> None:
    assert classify_gap(5, small_gap_max=5, medium_gap_max=20) == "small"
    assert classify_gap(6, small_gap_max=5, medium_gap_max=20) == "medium"
    assert classify_gap(20, small_gap_max=5, medium_gap_max=20) == "medium"
    assert classify_gap(21, small_gap_max=5, medium_gap_max=20) == "large"


def test_find_gaps_detects_no_gap_in_contiguous_data() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _candles(start, 10, timedelta(minutes=15))

    assert find_gaps(df, "15m", small_gap_max=5, medium_gap_max=20) == []


def test_find_gaps_detects_small_gap() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _candles(start, 10, timedelta(minutes=15), skip={3, 4})

    gaps = find_gaps(df, "15m", small_gap_max=5, medium_gap_max=20)

    assert len(gaps) == 1
    assert gaps[0].missing_candles == 2
    assert gaps[0].severity == "small"


def test_find_gaps_detects_large_gap() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _candles(start, 30, timedelta(minutes=15), skip=set(range(3, 25)))

    gaps = find_gaps(df, "15m", small_gap_max=5, medium_gap_max=20)

    assert len(gaps) == 1
    assert gaps[0].severity == "large"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_validator.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify_gap' from 'data.validator'`

- [ ] **Step 3: Implement gap detection (append to `backend/data/validator.py`)**

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

_TIMEFRAME_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    unit = timeframe[-1]
    if unit not in _TIMEFRAME_UNITS:
        raise ValueError(f"Unsupported timeframe unit: {timeframe!r}")
    amount = int(timeframe[:-1])
    return timedelta(**{_TIMEFRAME_UNITS[unit]: amount})


@dataclass(frozen=True)
class Gap:
    start: datetime
    end: datetime
    missing_candles: int
    severity: str


def classify_gap(missing_candles: int, small_gap_max: int, medium_gap_max: int) -> str:
    if missing_candles <= small_gap_max:
        return "small"
    if missing_candles <= medium_gap_max:
        return "medium"
    return "large"


def find_gaps(
    df: pl.DataFrame,
    timeframe: str,
    small_gap_max: int,
    medium_gap_max: int,
) -> list[Gap]:
    interval = timeframe_to_timedelta(timeframe)
    timestamps = df["timestamp"].to_list()
    gaps: list[Gap] = []

    for previous, current in zip(timestamps, timestamps[1:]):
        expected_next = previous + interval
        if current == expected_next:
            continue
        missing_candles = int((current - previous) / interval) - 1
        gaps.append(
            Gap(
                start=expected_next,
                end=current - interval,
                missing_candles=missing_candles,
                severity=classify_gap(missing_candles, small_gap_max, medium_gap_max),
            )
        )

    return gaps
```

Place the `from dataclasses import dataclass` and `from datetime import datetime, timedelta` imports at the top of `backend/data/validator.py` alongside the existing imports (remove any duplicate `import` lines).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_validator.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Checkpoint**

Re-run `pytest tests/data -v` and confirm all tests pass. Do not run any git commands.

---

### Task 5: Storage — metadata model, dataset paths, atomic write

**Files:**
- Create: `backend/data/storage.py`
- Test: `backend/tests/data/test_storage.py`

**Interfaces:**
- Consumes: `data.config.DownloadConfig` (Task 2), `data.validator.Gap` / `data.validator.find_gaps` (Task 4).
- Produces:
  - `data.storage.DatasetPaths` (`@dataclass(frozen=True)`: `parquet_path: Path`, `metadata_path: Path`)
  - `data.storage.dataset_paths(base_dir: Path, exchange: str, symbol_slug: str, timeframe: str) -> DatasetPaths`
  - `data.storage.DatasetMetadata` (Pydantic `BaseModel`: `schema_version: int`, `symbol: str`, `timeframe: str`, `exchange: str`, `status: str`, `start: datetime`, `end: datetime`, `row_count: int`, `gaps: list[GapRecord]`, `last_updated: datetime`)
  - `data.storage.read_parquet_if_exists(path: Path) -> pl.DataFrame | None`
  - `data.storage.read_metadata_if_exists(path: Path) -> DatasetMetadata | None`
  - `data.storage.build_metadata(df: pl.DataFrame, config: DownloadConfig, gaps: list[Gap], status: str) -> DatasetMetadata`
  - `data.storage.reconcile_metadata(df: pl.DataFrame, metadata: DatasetMetadata | None, config: DownloadConfig) -> DatasetMetadata | None`
  - `data.storage.atomic_write(df: pl.DataFrame, metadata: DatasetMetadata, paths: DatasetPaths) -> None`

  These are consumed directly by Task 7 (pipeline).

- [ ] **Step 1: Write the failing tests**

`backend/tests/data/test_storage.py`:

```python
from datetime import datetime, timezone

import polars as pl
import pytest

from data.config import DownloadConfig
from data.storage import (
    atomic_write,
    build_metadata,
    dataset_paths,
    read_metadata_if_exists,
    read_parquet_if_exists,
    reconcile_metadata,
)


def _config(**overrides) -> DownloadConfig:
    kwargs = {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "start": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    kwargs.update(overrides)
    return DownloadConfig(**kwargs)


def _df(*timestamps: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"timestamp": ts, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
            for ts in timestamps
        ]
    )


def test_dataset_paths_uses_symbol_slug(tmp_path) -> None:
    paths = dataset_paths(tmp_path, "binance", "BTCUSDT", "15m")

    assert paths.parquet_path == tmp_path / "ohlcv" / "binance" / "BTCUSDT" / "15m.parquet"
    assert paths.metadata_path == tmp_path / "ohlcv" / "binance" / "BTCUSDT" / "15m.metadata.json"


def test_read_parquet_if_exists_returns_none_when_missing(tmp_path) -> None:
    assert read_parquet_if_exists(tmp_path / "missing.parquet") is None


def test_read_metadata_if_exists_returns_none_when_missing(tmp_path) -> None:
    assert read_metadata_if_exists(tmp_path / "missing.metadata.json") is None


def test_atomic_write_creates_parquet_and_metadata(tmp_path) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _df(t0)
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status="complete")

    atomic_write(df, metadata, paths)

    assert paths.parquet_path.exists()
    assert paths.metadata_path.exists()
    assert not paths.parquet_path.with_name(paths.parquet_path.name + ".tmp").exists()
    reloaded = read_parquet_if_exists(paths.parquet_path)
    assert reloaded.height == 1
    reloaded_metadata = read_metadata_if_exists(paths.metadata_path)
    assert reloaded_metadata.status == "complete"
    assert reloaded_metadata.schema_version == 1


def test_atomic_write_failure_preserves_previous_dataset(tmp_path, monkeypatch) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _df(t0)
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    metadata = build_metadata(df, config, gaps=[], status="complete")
    atomic_write(df, metadata, paths)

    original_parquet_bytes = paths.parquet_path.read_bytes()
    original_metadata_text = paths.metadata_path.read_text()

    def _boom(self, *_args, **_kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _boom)

    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    new_df = _df(t0, t1)
    new_metadata = build_metadata(new_df, config, gaps=[], status="complete")

    with pytest.raises(RuntimeError):
        atomic_write(new_df, new_metadata, paths)

    assert paths.parquet_path.read_bytes() == original_parquet_bytes
    assert paths.metadata_path.read_text() == original_metadata_text
    assert not paths.parquet_path.with_name(paths.parquet_path.name + ".tmp").exists()


def test_reconcile_metadata_returns_unchanged_when_matching(tmp_path) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = _df(t0)
    metadata = build_metadata(df, config, gaps=[], status="complete")

    reconciled = reconcile_metadata(df, metadata, config)

    assert reconciled == metadata


def test_reconcile_metadata_regenerates_when_parquet_disagrees(tmp_path) -> None:
    config = _config()
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    df = _df(t0, t1)
    stale_metadata = build_metadata(_df(t0), config, gaps=[], status="complete")

    reconciled = reconcile_metadata(df, stale_metadata, config)

    assert reconciled.end == t1
    assert reconciled.row_count == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.storage'`

- [ ] **Step 3: Implement storage**

`backend/data/storage.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from pydantic import BaseModel

from data.config import DownloadConfig
from data.validator import Gap, find_gaps

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class GapRecord(BaseModel):
    start: datetime
    end: datetime
    missing_candles: int
    severity: str


class DatasetMetadata(BaseModel):
    schema_version: int = SCHEMA_VERSION
    symbol: str
    timeframe: str
    exchange: str
    status: str
    start: datetime
    end: datetime
    row_count: int
    gaps: list[GapRecord]
    last_updated: datetime


@dataclass(frozen=True)
class DatasetPaths:
    parquet_path: Path
    metadata_path: Path


def dataset_paths(base_dir: Path, exchange: str, symbol_slug: str, timeframe: str) -> DatasetPaths:
    directory = base_dir / "ohlcv" / exchange / symbol_slug
    return DatasetPaths(
        parquet_path=directory / f"{timeframe}.parquet",
        metadata_path=directory / f"{timeframe}.metadata.json",
    )


def read_parquet_if_exists(path: Path) -> pl.DataFrame | None:
    if not path.exists():
        return None
    return pl.read_parquet(path)


def read_metadata_if_exists(path: Path) -> DatasetMetadata | None:
    if not path.exists():
        return None
    return DatasetMetadata.model_validate_json(path.read_text())


def build_metadata(
    df: pl.DataFrame,
    config: DownloadConfig,
    gaps: list[Gap],
    status: str,
) -> DatasetMetadata:
    timestamps = df["timestamp"]
    return DatasetMetadata(
        symbol=config.symbol,
        timeframe=config.timeframe,
        exchange=config.exchange,
        status=status,
        start=timestamps.min(),
        end=timestamps.max(),
        row_count=df.height,
        gaps=[
            GapRecord(start=g.start, end=g.end, missing_candles=g.missing_candles, severity=g.severity)
            for g in gaps
        ],
        last_updated=datetime.now(timezone.utc),
    )


def reconcile_metadata(
    df: pl.DataFrame,
    metadata: DatasetMetadata | None,
    config: DownloadConfig,
) -> DatasetMetadata | None:
    if metadata is None:
        return None

    actual_end = df["timestamp"].max()
    if actual_end == metadata.end:
        return metadata

    logger.warning(
        "Metadata end %s disagrees with Parquet last timestamp %s; regenerating metadata",
        metadata.end,
        actual_end,
    )
    gaps = find_gaps(df, config.timeframe, config.small_gap_max, config.medium_gap_max)
    status = "incomplete" if gaps else "complete"
    return build_metadata(df, config, gaps, status)


def atomic_write(df: pl.DataFrame, metadata: DatasetMetadata, paths: DatasetPaths) -> None:
    paths.parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_tmp = paths.parquet_path.with_name(paths.parquet_path.name + ".tmp")
    metadata_tmp = paths.metadata_path.with_name(paths.metadata_path.name + ".tmp")

    try:
        df.write_parquet(parquet_tmp)
        metadata_tmp.write_text(metadata.model_dump_json(indent=2))
        parquet_tmp.replace(paths.parquet_path)
        metadata_tmp.replace(paths.metadata_path)
    except Exception:
        parquet_tmp.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_storage.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Checkpoint**

Re-run `pytest tests/data -v` and confirm all tests pass. Do not run any git commands.

---

### Task 6: Client — CCXT wrapper and paginated fetch

**Files:**
- Create: `backend/data/client.py`
- Test: `backend/tests/data/test_client.py`

**Interfaces:**
- Consumes: `data.validator.timeframe_to_timedelta` (Task 4).
- Produces:
  - `data.client.OHLCVFetcher` (`typing.Protocol` with `fetch_ohlcv(self, symbol: str, timeframe: str, since: int, limit: int) -> list[list[float]]`)
  - `data.client.create_ccxt_fetcher(exchange: str) -> OHLCVFetcher`
  - `data.client.fetch_ohlcv_range(fetcher: OHLCVFetcher, symbol: str, timeframe: str, start: datetime, end: datetime, limit: int = 1000) -> pl.DataFrame` — returns a DataFrame with the same `timestamp`/`open`/`high`/`low`/`close`/`volume` schema used throughout `data`.

  `fetch_ohlcv_range` and `OHLCVFetcher` are consumed directly by Task 7 (pipeline) and Task 8 (CLI, via `create_ccxt_fetcher`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/data/test_client.py`:

```python
from datetime import datetime, timedelta, timezone

from data.client import fetch_ohlcv_range


class ListFetcher:
    def __init__(self, candles: list[list[float]]) -> None:
        self._candles = candles

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return [c for c in self._candles if c[0] >= since][:limit]


def _candle(ts: datetime, price: float) -> list[float]:
    return [int(ts.timestamp() * 1000), price, price, price, price, 1.0]


def test_fetch_ohlcv_range_paginates_across_multiple_batches() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    interval = timedelta(minutes=15)
    candles = [_candle(start + i * interval, 100.0 + i) for i in range(5)]
    fetcher = ListFetcher(candles)

    df = fetch_ohlcv_range(fetcher, "BTC/USDT", "15m", start, start + 4 * interval, limit=2)

    assert df.height == 5
    assert df["timestamp"].to_list() == [start + i * interval for i in range(5)]
    assert df.columns == ["timestamp", "open", "high", "low", "close", "volume"]


def test_fetch_ohlcv_range_returns_empty_dataframe_when_no_data() -> None:
    fetcher = ListFetcher([])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    df = fetch_ohlcv_range(fetcher, "BTC/USDT", "15m", start, start)

    assert df.height == 0
    assert df.columns == ["timestamp", "open", "high", "low", "close", "volume"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.client'`

- [ ] **Step 3: Implement the client module**

`backend/data/client.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import ccxt
import polars as pl

from data.validator import timeframe_to_timedelta

DEFAULT_PAGE_LIMIT = 1000


class OHLCVFetcher(Protocol):
    def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int, limit: int
    ) -> list[list[float]]: ...


def create_ccxt_fetcher(exchange: str) -> OHLCVFetcher:
    exchange_class = getattr(ccxt, exchange)
    return exchange_class({"enableRateLimit": True})


def fetch_ohlcv_range(
    fetcher: OHLCVFetcher,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> pl.DataFrame:
    interval_ms = int(timeframe_to_timedelta(timeframe).total_seconds() * 1000)
    since_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    rows: list[list[float]] = []
    while since_ms <= end_ms:
        batch = fetcher.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        if not batch:
            break
        rows.extend(candle for candle in batch if candle[0] <= end_ms)
        last_ts = batch[-1][0]
        if last_ts > end_ms or len(batch) < limit:
            break
        since_ms = last_ts + interval_ms

    return _rows_to_dataframe(rows)


def _rows_to_dataframe(rows: list[list[float]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        )
    return pl.DataFrame(
        {
            "timestamp": [datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc) for row in rows],
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [row[5] for row in rows],
        }
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint**

Re-run `pytest tests/data -v` and confirm all tests pass. Do not run any git commands.

---

### Task 7: Pipeline — orchestration

**Files:**
- Create: `backend/data/pipeline.py`
- Test: `backend/tests/data/test_pipeline.py`

**Interfaces:**
- Consumes: `data.client.OHLCVFetcher` / `fetch_ohlcv_range` (Task 6), `data.config.DownloadConfig` (Task 2), `data.exceptions.DataIntegrityError` (Task 1), `data.storage.*` (Task 5), `data.validator.*` (Tasks 3–4).
- Produces: `data.pipeline.PipelineResult` (`@dataclass(frozen=True)`: `status: str`, `row_count: int`, `gaps: list[Gap]`) and `data.pipeline.run(config: DownloadConfig, fetcher: OHLCVFetcher, base_dir: Path) -> PipelineResult`. Consumed directly by Task 8 (CLI).

- [ ] **Step 1: Write the failing tests**

`backend/tests/data/test_pipeline.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from data.config import DownloadConfig
from data.exceptions import DataIntegrityError
from data.pipeline import run
from data.storage import atomic_write, build_metadata, dataset_paths

INTERVAL = timedelta(minutes=15)
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


class ListFetcher:
    def __init__(self, candles: list[list[float]]) -> None:
        self._candles = candles

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return [c for c in self._candles if c[0] >= since][:limit]


def _candle(ts: datetime, price: float = 100.0) -> list[float]:
    return [int(ts.timestamp() * 1000), price, price, price, price, 1.0]


def _contiguous_candles(count: int, skip: set[int] | None = None) -> list[list[float]]:
    skip = skip or set()
    return [_candle(START + i * INTERVAL, 100.0 + i) for i in range(count) if i not in skip]


def _config(**overrides) -> DownloadConfig:
    kwargs = {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "start": START,
        "end": START + 19 * INTERVAL,
        "retry_count": 1,
    }
    kwargs.update(overrides)
    return DownloadConfig(**kwargs)


def _seed_dataframe(count: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * INTERVAL for i in range(count)],
            "open": [100.0 + i for i in range(count)],
            "high": [100.0 + i for i in range(count)],
            "low": [100.0 + i for i in range(count)],
            "close": [100.0 + i for i in range(count)],
            "volume": [1.0 for _ in range(count)],
        }
    )


def test_run_full_download_with_no_gaps_marks_complete(tmp_path: Path) -> None:
    config = _config()
    fetcher = ListFetcher(_contiguous_candles(20))

    result = run(config, fetcher, tmp_path)

    assert result.status == "complete"
    assert result.row_count == 20
    assert result.gaps == []
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    assert paths.parquet_path.exists()
    assert paths.metadata_path.exists()


def test_run_incremental_only_fetches_delta(tmp_path: Path) -> None:
    config = _config()
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)
    seed_df = _seed_dataframe(10)
    seed_metadata = build_metadata(seed_df, config, gaps=[], status="complete")
    atomic_write(seed_df, seed_metadata, paths)

    fetcher = ListFetcher(_contiguous_candles(20))
    result = run(config, fetcher, tmp_path)

    assert result.status == "complete"
    assert result.row_count == 20


def test_run_unresolved_small_gap_marks_incomplete(tmp_path: Path) -> None:
    config = _config(end=START + 19 * INTERVAL, retry_count=1)
    fetcher = ListFetcher(_contiguous_candles(20, skip={5}))

    result = run(config, fetcher, tmp_path)

    assert result.status == "incomplete"
    assert len(result.gaps) == 1
    assert result.gaps[0].severity == "small"
    assert result.gaps[0].missing_candles == 1


def test_run_unresolved_medium_gap_marks_incomplete(tmp_path: Path) -> None:
    config = _config(end=START + 29 * INTERVAL, retry_count=1)
    fetcher = ListFetcher(_contiguous_candles(30, skip=set(range(5, 13))))

    result = run(config, fetcher, tmp_path)

    assert result.status == "incomplete"
    assert len(result.gaps) == 1
    assert result.gaps[0].severity == "medium"
    assert result.gaps[0].missing_candles == 8


def test_run_large_gap_raises_and_preserves_previous_dataset(tmp_path: Path) -> None:
    config = _config(end=START + 29 * INTERVAL)
    paths = dataset_paths(tmp_path, config.exchange, config.symbol_slug, config.timeframe)

    seed_df = _seed_dataframe(1)
    seed_metadata = build_metadata(seed_df, config, gaps=[], status="complete")
    atomic_write(seed_df, seed_metadata, paths)
    original_parquet_bytes = paths.parquet_path.read_bytes()
    original_metadata_text = paths.metadata_path.read_text()

    fetcher = ListFetcher(_contiguous_candles(30, skip=set(range(2, 25))))

    with pytest.raises(DataIntegrityError):
        run(config, fetcher, tmp_path)

    assert paths.parquet_path.read_bytes() == original_parquet_bytes
    assert paths.metadata_path.read_text() == original_metadata_text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.pipeline'`

- [ ] **Step 3: Implement the pipeline**

`backend/data/pipeline.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from data.client import OHLCVFetcher, fetch_ohlcv_range
from data.config import DownloadConfig
from data.exceptions import DataIntegrityError
from data.storage import (
    atomic_write,
    build_metadata,
    dataset_paths,
    read_metadata_if_exists,
    read_parquet_if_exists,
    reconcile_metadata,
)
from data.validator import Gap, deduplicate, find_gaps, sort_by_timestamp, timeframe_to_timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    status: str
    row_count: int
    gaps: list[Gap]


def run(config: DownloadConfig, fetcher: OHLCVFetcher, base_dir: Path) -> PipelineResult:
    paths = dataset_paths(base_dir, config.exchange, config.symbol_slug, config.timeframe)
    existing_df = read_parquet_if_exists(paths.parquet_path)
    interval = timeframe_to_timedelta(config.timeframe)

    if existing_df is not None:
        existing_metadata = read_metadata_if_exists(paths.metadata_path)
        reconcile_metadata(existing_df, existing_metadata, config)
        fetch_start = existing_df["timestamp"].max() + interval
    else:
        fetch_start = config.start

    fetch_end = config.end or datetime.now(timezone.utc)

    new_df = fetch_ohlcv_range(fetcher, config.symbol, config.timeframe, fetch_start, fetch_end)
    merged_df = pl.concat([existing_df, new_df]) if existing_df is not None else new_df
    merged_df = sort_by_timestamp(merged_df)
    merged_df = deduplicate(merged_df)

    gaps = find_gaps(merged_df, config.timeframe, config.small_gap_max, config.medium_gap_max)
    large_gaps = [g for g in gaps if g.severity == "large"]
    if large_gaps:
        first = large_gaps[0]
        raise DataIntegrityError(
            f"Large gap of {first.missing_candles} missing candles between "
            f"{first.start} and {first.end}",
            start=str(first.start),
            end=str(first.end),
        )

    unresolved_gaps = [g for g in gaps if g.severity in ("small", "medium")]

    for _attempt in range(config.retry_count):
        if not unresolved_gaps:
            break
        for gap in list(unresolved_gaps):
            refetched = fetch_ohlcv_range(fetcher, config.symbol, config.timeframe, gap.start, gap.end)
            if refetched.height == 0:
                continue
            merged_df = pl.concat([merged_df, refetched])
            merged_df = sort_by_timestamp(merged_df)
            merged_df = deduplicate(merged_df)
        unresolved_gaps = [
            g
            for g in find_gaps(merged_df, config.timeframe, config.small_gap_max, config.medium_gap_max)
            if g.severity in ("small", "medium")
        ]

    for gap in unresolved_gaps:
        logger.warning(
            "Unresolved %s gap of %d candles between %s and %s after %d retries",
            gap.severity,
            gap.missing_candles,
            gap.start,
            gap.end,
            config.retry_count,
        )

    status = "incomplete" if unresolved_gaps else "complete"
    metadata = build_metadata(merged_df, config, unresolved_gaps, status)
    atomic_write(merged_df, metadata, paths)

    return PipelineResult(status=status, row_count=merged_df.height, gaps=unresolved_gaps)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_pipeline.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Checkpoint**

Re-run `pytest tests/data -v` and confirm all tests pass. Do not run any git commands.

---

### Task 8: CLI entry point

**Files:**
- Create: `backend/data/cli.py`
- Test: `backend/tests/data/test_cli.py`

**Interfaces:**
- Consumes: `data.client.create_ccxt_fetcher` (Task 6), `data.config.DownloadConfig` (Task 2), `data.exceptions.DataIntegrityError` (Task 1), `data.pipeline.run` (Task 7).
- Produces: `data.cli.build_parser() -> argparse.ArgumentParser`, `data.cli.main(argv: list[str] | None = None) -> int` (0 on success, 1 on `DataIntegrityError`), and module-level `data.cli.DEFAULT_DATA_DIR: Path`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/data/test_cli.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import data.cli as cli_module
from data.cli import build_parser, main

INTERVAL = timedelta(minutes=15)
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


class ListFetcher:
    def __init__(self, candles):
        self._candles = candles

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return [c for c in self._candles if c[0] >= since][:limit]


def _candle(ts, price=100.0):
    return [int(ts.timestamp() * 1000), price, price, price, price, 1.0]


def test_build_parser_parses_download_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["download", "--symbol", "BTC/USDT", "--timeframe", "15m", "--start", "2024-01-01T00:00:00"]
    )

    assert args.symbol == "BTC/USDT"
    assert args.timeframe == "15m"
    assert args.retry_count == 1


def test_main_returns_zero_on_successful_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", tmp_path)
    candles = [_candle(START + i * INTERVAL, 100.0 + i) for i in range(5)]
    monkeypatch.setattr(cli_module, "create_ccxt_fetcher", lambda exchange: ListFetcher(candles))

    exit_code = main(
        [
            "download",
            "--symbol", "BTC/USDT",
            "--timeframe", "15m",
            "--start", "2024-01-01T00:00:00",
            "--end", "2024-01-01T01:00:00",
        ]
    )

    assert exit_code == 0


def test_main_returns_one_on_data_integrity_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", tmp_path)
    candles = [_candle(START + i * INTERVAL, 100.0 + i) for i in range(30) if i not in set(range(2, 25))]
    monkeypatch.setattr(cli_module, "create_ccxt_fetcher", lambda exchange: ListFetcher(candles))

    exit_code = main(
        [
            "download",
            "--symbol", "BTC/USDT",
            "--timeframe", "15m",
            "--start", "2024-01-01T00:00:00",
            "--end", "2024-01-01T07:15:00",
        ]
    )

    assert exit_code == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data.cli'`

- [ ] **Step 3: Implement the CLI**

`backend/data/cli.py`:

```python
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from data.client import create_ccxt_fetcher
from data.config import DownloadConfig
from data.exceptions import DataIntegrityError
from data.pipeline import run

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.data.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download and validate OHLCV data")
    download.add_argument("--symbol", required=True)
    download.add_argument("--timeframe", required=True)
    download.add_argument("--start", required=True, type=_parse_datetime)
    download.add_argument("--end", type=_parse_datetime, default=None)
    download.add_argument("--exchange", default="binance")
    download.add_argument("--small-gap-max", type=int, default=5, dest="small_gap_max")
    download.add_argument("--medium-gap-max", type=int, default=20, dest="medium_gap_max")
    download.add_argument("--retry-count", type=int, default=1, dest="retry_count")

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = build_parser()
    args = parser.parse_args(argv)

    config = DownloadConfig(
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        small_gap_max=args.small_gap_max,
        medium_gap_max=args.medium_gap_max,
        retry_count=args.retry_count,
    )
    fetcher = create_ccxt_fetcher(config.exchange)

    try:
        result = run(config, fetcher, DEFAULT_DATA_DIR)
    except DataIntegrityError as error:
        logging.getLogger(__name__).error("Data integrity check failed: %s", error)
        return 1

    logging.getLogger(__name__).info(
        "Download finished with status=%s row_count=%d", result.status, result.row_count
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/data/test_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Checkpoint**

Run the full suite: `pytest tests/data -v` from `backend/`. Expected: all tests across Tasks 1–8 pass (30 passed). Do not run any git commands.

---

### Task 9: Module README

**Files:**
- Create: `backend/data/README.md`

- [ ] **Step 1: Write the README**

`backend/data/README.md`:

```markdown
# data — OHLCV Data Pipeline

Downloads OHLCV candles from Binance Spot via CCXT, validates them, and
persists them to Parquet with a JSON metadata sidecar. This is the only
module in Phase 1 that touches an external data source.

## Modules

- `config.py` — `DownloadConfig` (Pydantic model): symbol, timeframe, date
  range, gap thresholds, retry count.
- `client.py` — CCXT wrapper (`create_ccxt_fetcher`) and paginated fetch
  (`fetch_ohlcv_range`). `OHLCVFetcher` is a `Protocol`, so tests inject a
  fake fetcher instead of hitting the network.
- `validator.py` — sorting, duplicate handling (`deduplicate`), and gap
  detection/classification (`find_gaps`, `classify_gap`).
- `storage.py` — Parquet + `{timeframe}.metadata.json` sidecar read/write,
  metadata reconciliation, and atomic (write-temp-then-rename) writes.
- `pipeline.py` — orchestrates the above: `run(config, fetcher, base_dir)`.
- `cli.py` — `python -m backend.data.cli download ...` entry point.
- `exceptions.py` — `DataIntegrityError`, raised whenever data cannot be
  safely persisted.

## Usage

```
python -m backend.data.cli download \
  --symbol BTC/USDT \
  --timeframe 15m \
  --start 2020-01-01T00:00:00 \
  [--end 2026-07-31T00:00:00] \
  [--exchange binance] \
  [--small-gap-max 5] \
  [--medium-gap-max 20] \
  [--retry-count 1]
```

Data is written to `Trader_v2/data/ohlcv/{exchange}/{symbol_slug}/{timeframe}.parquet`
with a matching `{timeframe}.metadata.json` sidecar.

## Gap policy

Gap size is measured in consecutive missing candles between two known
candles:

| Severity | Range | Behavior |
|---|---|---|
| Small | `<= small_gap_max` (default 5) | Retry `retry_count` times; if still missing, warn and mark dataset `incomplete`. |
| Medium | `small_gap_max` < n `<= medium_gap_max` (default 6-20) | Retry `retry_count` times; if still missing, warn and mark dataset `incomplete`. |
| Large | `> medium_gap_max` (default > 20) | Fail immediately (`DataIntegrityError`), no data is written, the previous valid dataset is untouched. |

This module only reports `status` (`complete`/`incomplete`) and per-gap
`severity` in the metadata sidecar. It does not decide whether an
incomplete dataset is acceptable for backtesting — that policy belongs to
the Backtesting Engine milestone.

## Testing

All tests use a fake/mocked CCXT fetcher (`ListFetcher` in the test files)
implementing the `OHLCVFetcher` protocol. No test performs a live network
call. Run with `pytest tests/data -v` from `backend/`.
```

- [ ] **Step 2: Checkpoint**

Confirm the file renders correctly and cross-check its content against
`storage.py`, `pipeline.py`, and `cli.py` for accuracy. Do not run any git
commands.

---

## Final Verification

- [ ] Run `pytest tests/data -v` from `backend/` one more time and confirm the full suite (30 tests across Tasks 1–8) passes.
- [ ] Confirm no test in `backend/tests/data/` makes a real network call (grep for `ccxt.binance()` or similar outside of `client.py`/`cli.py` — there should be none in the test files).
- [ ] Confirm no `git init` or `git commit` was run anywhere during this plan's execution.

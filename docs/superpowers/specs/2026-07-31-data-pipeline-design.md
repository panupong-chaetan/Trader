# Data Pipeline — Milestone Design

Date: 2026-07-31
Project: Trader v2 — Phase 1
Milestone: Data Pipeline (OHLCV download, validation, Parquet storage)

## Overview

Build the foundational data module for Trader v2: download OHLCV candles from
Binance Spot via CCXT, validate the result (missing candles, duplicates, time
order), persist it to Parquet with a JSON metadata sidecar, and support
incremental updates. This is the first module of Phase 1 — the Backtesting
Engine and later milestones will consume the datasets this module produces.

## Goals

- Download OHLCV for a single symbol + single timeframe from Binance Spot.
- Detect and handle missing candles, duplicate candles, and out-of-order
  candles according to explicit, deterministic rules (no silent data
  mutation without logging).
- Persist validated data to Parquet, partitioned by exchange/symbol/timeframe.
- Track dataset status (complete/incomplete) in a metadata sidecar file.
- Support incremental (delta) downloads using the Parquet file itself as the
  source of truth for "where did we leave off."
- Protect existing valid data: a failed or partially-invalid update must
  never corrupt or discard the last known-good dataset.
- CLI entry point for manual/scripted invocation.

## Non-Goals (excluded from this milestone)

- Multiple symbols or timeframes in a single run (config supports one of
  each; batching is a future milestone).
- Supabase integration.
- REST API endpoints.
- Backtesting Engine, Strategy, Risk, or Analytics modules.
- Any data source other than Binance Spot via CCXT.

## Architecture

Flat, function-oriented modules, one responsibility per file, no shared
mutable state. Dependency direction: `cli` → `pipeline` → (`client`,
`validator`, `storage`) → `config`.

```
Trader_v2/
  backend/
    data/
      __init__.py
      config.py        # DownloadConfig Pydantic model (symbol, timeframe, start, end, gap thresholds)
      client.py        # CCXT Binance wrapper: paginated fetch_ohlcv
      validator.py     # missing-candle / duplicate / time-order checks, gap classification
      storage.py        # Parquet + metadata sidecar read/write, atomic write logic
      pipeline.py        # orchestrates: read-existing -> fetch delta -> validate -> merge -> atomic write
      exceptions.py        # DataIntegrityError and related typed exceptions
      cli.py                 # `python -m backend.data.cli download ...`
    tests/
      data/
        test_validator.py
        test_storage.py
        test_pipeline.py    # uses a fake/mocked CCXT client, no live network calls
  data/
    ohlcv/
      binance/
        BTCUSDT/
          15m.parquet
          15m.metadata.json
```

Rationale for this shape over alternatives: a single combined module would
blur validation/storage boundaries the project rules require; a
Repository/class-based abstraction would be premature given Phase 1 is
explicitly single-exchange, single-source.

Storage paths use the symbol with separators stripped (`BTC/USDT` →
`BTCUSDT`) so directory names stay filesystem- and URL-safe; the
metadata sidecar retains the original `symbol` string (`"BTC/USDT"`) for
display and re-querying via CCXT.

## Configuration

`DownloadConfig` (Pydantic `BaseModel`, all fields explicit — no hidden
defaults that affect correctness; Pydantic gives us input validation for
free, e.g. `start < end`, positive gap thresholds, valid timeframe strings):

```python
class DownloadConfig(BaseModel):
    exchange: str              # "binance"
    symbol: str                # "BTC/USDT"
    timeframe: str              # "15m"
    start: datetime              # required, user-specified
    end: datetime | None = None     # None = up to now
    small_gap_max: int = 5             # <= this many consecutive missing candles
    medium_gap_max: int = 20            # <= this many consecutive missing candles
    # > medium_gap_max is treated as a large gap
    retry_count: int = 1                 # retries for small/medium gap sub-ranges before giving up
```

## Data Flow

1. CLI parses arguments and builds a `DownloadConfig`.
2. `pipeline.run(config)`:
   a. If a Parquet file already exists for this exchange/symbol/timeframe,
      read it and take the **last timestamp in the Parquet file itself**
      (not the metadata sidecar) as the incremental start point. See
      "Incremental Update Logic."
   b. Fetch OHLCV in paginated batches from `start` to `end` via `client.py`.
   c. Run validation (`validator.py`) on the fetched batch: time order,
      duplicates, missing candles/gaps (see "Validation Rules").
   d. If large gaps are found: raise `DataIntegrityError`, abort the run,
      leave the existing Parquet + metadata files untouched.
   e. If small/medium gaps are found: retry the missing sub-ranges up to
      `config.retry_count` times via `client.py`. Re-validate. Apply the
      resulting status per "Gap Behavior."
   f. Merge validated new data with existing Parquet data (if any).
   g. Atomically write the merged Parquet file and regenerated metadata
      sidecar (see "Atomic Write").

## Validation Rules

### Time order

- After fetching, sort all candles by timestamp ascending.
- Re-run validation (duplicate check, gap check) on the sorted data.
- If the data is still invalid after sorting (e.g., unresolvable duplicate
  conflicts — see below), the run fails. Out-of-order input alone is never a
  failure condition; it's corrected by sorting.

### Duplicates (identical timestamp)

- Identical timestamp **and** identical OHLCV values: treat as a duplicate,
  drop the extra row(s), log an info-level message with the timestamp and
  count removed.
- Identical timestamp **but conflicting OHLCV values**: raise
  `DataIntegrityError` immediately. Do not silently keep either row — this
  indicates a data-source inconsistency that must be investigated manually.

### Missing candles (gaps)

Gap size = number of consecutive missing candle slots between two known
candles, based on the timeframe's expected interval.

| Gap size (consecutive candles) | Classification | Threshold source |
|---|---|---|
| ≤ `small_gap_max` (default 5) | Small | `config.small_gap_max` |
| `small_gap_max` < n ≤ `medium_gap_max` (default 6–20) | Medium | `config.medium_gap_max` |
| > `medium_gap_max` (default > 20) | Large | derived |

## Gap Behavior

The Data Pipeline's only responsibility is to detect gaps, attempt recovery,
and honestly report what it found. It does not decide whether a dataset is
fit for backtesting — that policy decision belongs to the Backtesting Engine
milestone, which will read `status` and the per-gap `severity` list from
metadata and apply its own acceptance rules.

- **Small gap**: retry the missing sub-range up to `config.retry_count`
  times. If still missing, log a warning, record the gap in metadata with
  `severity: "small"`, and mark the dataset `incomplete`. The pipeline still
  completes and writes the data.
- **Medium gap**: retry the missing sub-range up to `config.retry_count`
  times. If still missing, log a warning, record the gap in metadata with
  `severity: "medium"`, and mark the dataset `incomplete`. The pipeline
  still completes and writes the data.
- **Large gap**: no retry. Validation fails outright. Raise
  `DataIntegrityError` describing the gap range and size. The pipeline
  aborts before any write — the previously persisted Parquet + metadata (if
  any) are left exactly as they were.

## Metadata Sidecar

File name: `{timeframe}.metadata.json`, stored alongside
`{timeframe}.parquet` in the same directory
(`data/ohlcv/{exchange}/{symbol}/`).

```json
{
  "schema_version": 1,
  "symbol": "BTC/USDT",
  "timeframe": "15m",
  "exchange": "binance",
  "status": "complete",
  "start": "2020-01-01T00:00:00Z",
  "end": "2026-07-31T00:00:00Z",
  "row_count": 123456,
  "gaps": [
    {"start": "...", "end": "...", "missing_candles": 3, "severity": "small"}
  ],
  "last_updated": "2026-07-31T18:00:00Z"
}
```

`status` is `"complete"` or `"incomplete"` — this is the only status the
Data Pipeline reports. `gaps[].severity` (`"small"` / `"medium"`) is
preserved so downstream consumers, such as the Backtesting Engine, can apply
their own acceptance policy; the Data Pipeline itself makes no
backtest-eligibility decision. `schema_version` allows the metadata format
to evolve without breaking older sidecar files; this milestone starts at
`1`.

**Metadata is supporting information only — the Parquet file is the source
of truth.** On every pipeline run:

1. Read the last timestamp directly from the Parquet file's data.
2. Compare it against `metadata.end`.
3. If they disagree, log a warning and **regenerate the metadata file from
   the Parquet data** (recompute `start`, `end`, `row_count`, and re-run gap
   detection over the existing Parquet data to rebuild `gaps`/`status`)
   before proceeding with the incremental fetch.

This also self-heals the case where a crash happens between writing the
Parquet file and writing the metadata file during an atomic write (see
below) — the next run detects the mismatch and regenerates metadata rather
than trusting stale sidecar state.

## Incremental Update Logic

- If no Parquet file exists: full download from `config.start`.
- If a Parquet file exists: the incremental fetch start point is
  `last_timestamp_in_parquet + 1 candle interval`, read directly from the
  Parquet file's data (not from metadata). Metadata is reconciled per the
  rule above before the delta fetch begins.
- Newly fetched data is validated independently, then merged with existing
  Parquet data (concatenate, sort, re-run duplicate check across the merge
  boundary) before writing.

## Atomic Write

Both the Parquet file and its metadata sidecar must move together from one
valid state to the next, and a failure at any point must leave the
previously persisted valid dataset intact:

1. Write the new merged data to a temp file in the same directory
   (`{timeframe}.parquet.tmp`).
2. Write the new metadata to a temp file (`{timeframe}.metadata.json.tmp`).
3. Only after both temp files are fully written and flushed: rename
   `{timeframe}.parquet.tmp` → `{timeframe}.parquet` (atomic on the same
   filesystem), then rename `{timeframe}.metadata.json.tmp` →
   `{timeframe}.metadata.json`.
4. If any step before the renames fails (fetch error, validation failure,
   write error), delete any temp files created and leave the existing
   `{timeframe}.parquet` / `{timeframe}.metadata.json` untouched.
5. If the process is interrupted between the two renames in step 3, the
   Parquet file is already valid and up to date; the next run's
   Parquet-vs-metadata reconciliation (see "Metadata Sidecar") regenerates
   the metadata file automatically.

## Error Handling

`exceptions.py` defines:

- `DataIntegrityError` — raised for: conflicting-OHLCV duplicates,
  data that remains invalid after sort, and large gaps. Carries the
  affected time range and a human-readable reason.

All raises happen before any write step; the CLI catches `DataIntegrityError`
at the top level, logs it, and exits non-zero. No partial state is ever
persisted.

## CLI

```
python -m backend.data.cli download \
  --symbol BTC/USDT \
  --timeframe 15m \
  --start 2020-01-01 \
  [--end 2026-07-31] \
  [--small-gap-max 5] \
  [--medium-gap-max 20] \
  [--retry-count 1]
```

Exit code 0 on success (including a run that completed with an `incomplete`
status), non-zero only on `DataIntegrityError` or unhandled exceptions.

## Testing Plan

- `test_validator.py`: pure unit tests on synthetic Polars DataFrames —
  small/medium/large gap classification at threshold boundaries,
  identical-duplicate dedup, conflicting-duplicate raises
  `DataIntegrityError`, out-of-order input that becomes valid after sort,
  out-of-order input that remains invalid after sort (fails).
- `test_storage.py`: atomic write success path; simulated failure mid-write
  leaves prior Parquet/metadata untouched; metadata regeneration when
  Parquet's last timestamp disagrees with stored metadata.
- `test_pipeline.py`: end-to-end using a fake/mocked CCXT client
  (dependency-injected) — full download, incremental delta download,
  retry-then-warn-and-mark-incomplete on unresolved small gap (respecting
  `config.retry_count`), retry-then-mark-incomplete with `severity: medium`
  on unresolved medium gap, immediate abort with dataset untouched on large
  gap (no retry attempted). No test performs a live network call.

## Known Limitations

- Single symbol/timeframe per run; no batch orchestration yet.
- No Supabase or REST API integration — this module is invoked via CLI only
  until the corresponding later milestones.
- Gap detection assumes a fixed, well-known candle interval per timeframe;
  exchange-side timeframe changes or irregular intervals are out of scope.

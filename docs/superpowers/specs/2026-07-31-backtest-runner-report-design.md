# Backtest Runner and Report — Milestone Design

Date: 2026-07-31
Project: Trader v2 — Phase 1
Milestone: Backtest Runner and Report

## Overview

Wire together the four existing, independently-tested modules — Data
Pipeline (`data`/`engine.loader`), Sample Strategy (`strategy`), Backtesting
Engine (`engine.backtester`), and a new reporting layer — into one CLI
command that runs a real end-to-end backtest and produces an honest,
structured report. No new simulation, sizing, or signal-generation logic is
introduced here; this milestone is orchestration plus reporting only.

## Goals

- `runner/cli.py`: one command that loads a dataset, generates EMA Trend
  Pullback signals, runs the Backtesting Engine, and writes a report.
- `report/builder.py`: pure calculation of a complete, honest summary from
  a `BacktestResult` — no simulation logic, no filesystem access.
- `report/export.py`: write `summary.json`, `trades.csv`,
  `equity_curve.parquet` to a **unique run directory per invocation** so
  earlier reports are never overwritten.
- Incomplete datasets are only usable via an explicit `--allow-incomplete-dataset`
  CLI flag (same pattern as the Data Pipeline CLI).
- A zero-trade result still produces a valid, correctly-columned
  `trades.csv`.
- No strategy parameter is exposed as a CLI flag — EMA/ATR/R-multiple stay
  fixed inside `strategy.ema_trend_pullback`.

## Non-Goals

- REST API, Supabase, frontend (explicitly excluded this milestone).
- Any change to `data`, `engine.backtester`, `risk`, `analytics`, or
  `strategy` — this milestone only adds new files and wires existing ones.
- Parameter optimization of any kind.

## Architecture

```
Trader_v2/
  backend/
    report/
      __init__.py
      builder.py       # build_summary() — pure, no I/O
      export.py          # write_summary_json/trades_csv/equity_curve_parquet
    runner/
      __init__.py
      cli.py              # orchestration: loader -> strategy -> engine -> report
    tests/
      report/
        test_builder.py
        test_export.py
      runner/
        test_cli.py
```

`report/builder.py` and `report/export.py` have no dependency on
`engine.backtester`'s internals — they only consume `engine.models.BacktestResult`
and plain values, matching the "reporting logic separate from the
simulation engine" requirement.

## Report Content (`report/builder.py`)

```python
@dataclass(frozen=True)
class GapWarning:
    start: datetime
    end: datetime
    severity: str


@dataclass(frozen=True)
class ReportSummary:
    symbol: str
    timeframe: str
    exchange: str
    dataset_start: datetime
    dataset_end: datetime
    dataset_status: str
    gap_warnings: list[GapWarning]
    config: BacktestConfig
    num_signals: int
    num_trades: int
    num_rejected_signals: int
    initial_equity: float
    final_equity: float
    net_pnl: float
    return_pct: float
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    max_consecutive_losses: int | None
    total_fees_paid: float
    exit_reason_counts: dict[str, int]


def build_summary(
    result: BacktestResult,
    num_signals: int,
    symbol: str,
    timeframe: str,
    exchange: str,
) -> ReportSummary: ...
```

- `dataset_start`/`dataset_end`: first/last timestamp of `result.equity_curve`
  (the range actually simulated), or both `None`-equivalent (empty curve)
  handled as the earliest/only available timestamp if the curve has exactly
  one row; an empty curve (zero rows — only possible with empty input data)
  is out of scope since the engine always produces at least one row when
  given at least one candle.
- `gap_warnings`: every gap in `result.dataset_quality.gaps` whose
  `[start, end]` overlaps `[dataset_start, dataset_end]` — computed
  independently here (not read from engine log output), so report content
  never depends on log-line parsing.
- `num_signals` is supplied by the caller (`runner/cli.py`), since it is the
  strategy's raw output count, not something `BacktestResult` tracks (the
  engine may silently skip a signal that arrives while a position is
  already open — that is expected behavior, not an error, and is visible in
  the report only as `num_signals - num_trades - num_rejected_signals > 0`
  if it happens).
- `initial_equity = result.config.initial_capital`.
- `final_equity` = the last value in `result.equity_curve`'s `equity`
  column.
- `net_pnl = final_equity - initial_equity`; `return_pct = net_pnl / initial_equity * 100`.
- `total_fees_paid = sum(t.entry_fee + t.exit_fee for t in result.trades)`
  (`0.0` when there are no trades).
- `exit_reason_counts`: a dict counting `result.trades` by `exit_reason`,
  containing only reasons that actually occurred (empty dict when there are
  no trades).

## Export (`report/export.py`)

```python
def write_summary_json(summary: ReportSummary, path: Path) -> None
def write_trades_csv(trades: list[Trade], path: Path) -> None
def write_equity_curve_parquet(equity_curve: pl.DataFrame, path: Path) -> None
```

- `write_summary_json`: converts `ReportSummary` to a plain `dict`
  (datetimes -> ISO 8601 strings, the nested `BacktestConfig` -> its own
  dict via Pydantic's `.model_dump()`, `GapWarning` list -> list of dicts),
  then `json.dump(..., indent=2)`. Python's `json` module serializes
  `float("inf")` as the token `Infinity` (a non-standard but widely-accepted
  extension, and the same one Python's own `json.load` reads back
  correctly) — this is accepted as-is rather than special-cased, and noted
  in Known Limitations.
- `write_trades_csv`: converts `trades` to a `pl.DataFrame` with an
  **explicit schema** matching every `Trade` field (not inferred from the
  data), so that an empty `trades` list still produces a CSV with the
  correct header row and zero data rows — satisfying the "zero-trade result
  still exports a valid trades.csv" requirement directly, rather than as an
  edge-case afterthought.
- `write_equity_curve_parquet`: `equity_curve.write_parquet(path)` directly
  — it is already the correctly-schemad `pl.DataFrame` produced by the
  engine.

## Unique Run Directories (`runner/cli.py`)

Every invocation creates its own subdirectory under `--output-dir` (default
`./reports`) so no previous run's files are ever overwritten:

```python
def _create_run_directory(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    run_dir = base_dir / f"run_{timestamp}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir
```

The `uuid` suffix (not just the timestamp) guards against two runs starting
within the same second producing a directory collision — `mkdir(exist_ok=False)`
would otherwise raise, which is the correct fail-safe behavior if a
collision ever did occur, but the suffix makes it practically unreachable.
`summary.json`, `trades.csv`, and `equity_curve.parquet` are all written
inside this one `run_dir`.

## CLI (`runner/cli.py`)

```
python -m backend.runner.cli \
  --symbol BTC/USDT --timeframe 15m --exchange binance \
  --output-dir ./reports \
  [--allow-incomplete-dataset] \
  [--initial-capital 10000] [--leverage 1.0] \
  [--risk-per-trade-pct 0.005] [--fee-pct 0.001] [--slippage-pct 0.0005]
```

No flags for EMA period, ATR period/multiplier, or R-multiple — those
remain fixed module-level constants inside `strategy.ema_trend_pullback`,
per "do not optimize any strategy parameters."

Flow:
1. `engine.loader.load_dataset(data_dir, exchange, symbol_slug, timeframe)`.
2. `strategy.ema_trend_pullback.generate_signals(ohlcv)` -> `signals`
   (`num_signals = len(signals)`).
3. `engine.backtester.run(ohlcv, signals, dataset_quality, config)` ->
   raises `DataIntegrityError` if the dataset is incomplete and
   `--allow-incomplete-dataset` was not passed (identical error-handling
   shape to the Data Pipeline CLI: caught at the top level, logged, exit
   code `1`).
4. `report.builder.build_summary(result, num_signals, symbol, timeframe, exchange)`.
5. Create the unique run directory; write all three export files into it.
6. Print the summary to the console, explicitly framed as a hypothesis
   test — e.g. a closing line such as `"This is a hypothesis test only —
   not a profitability claim."` — consistent with the project's own
   Development Rules ("ทุก Strategy ถือเป็นเพียง Hypothesis").
7. Exit code `0` on success (including a losing or zero-trade backtest —
   those are valid, non-error outcomes), `1` on `DataIntegrityError`.

## Testing Strategy

- `test_builder.py`: hand-built `BacktestResult` (small, fully known
  `trades`, `equity_curve`, `dataset_quality`, `config`) -> every
  `ReportSummary` field asserted, including: gap-overlap detection (a gap
  fully inside the range, a gap fully outside, a gap partially overlapping
  the boundary), zero-trade case (`total_fees_paid == 0.0`,
  `exit_reason_counts == {}`, `win_rate is None` from the underlying
  metrics), and `return_pct` sign for both winning and losing scenarios.
- `test_export.py`: round-trip tests in `tmp_path` — write then re-read
  `summary.json` (compare key fields, including an `inf` profit factor
  round-tripping correctly), `trades.csv` (including the **zero-trade
  case**: assert the file has a header row with every `Trade` field name
  and zero data rows), `equity_curve.parquet` (write then
  `pl.read_parquet`, compare to the original).
- `test_cli.py`: a synthetic dataset written via `data.storage` into
  `tmp_path` (mirroring the `engine/loader` tests) —
  - Incomplete dataset without the flag: exit code `1`, no run directory
    created.
  - Incomplete dataset with the flag: exit code `0`, run directory created
    with all three files.
  - Two consecutive invocations against the same `--output-dir` produce
    **two distinct run directories**, both fully intact (the concrete test
    for the "unique run directory" requirement).
  - A dataset/signal combination engineered to produce zero trades still
    exits `0` and produces a valid `trades.csv`.

## Real Verification

After implementation and the full test suite passing, run the CLI once
against the real BTC/USDT 15m dataset already on disk
(`data/ohlcv/binance/BTCUSDT/15m.parquet`, currently `status: incomplete`):
first without `--allow-incomplete-dataset` to confirm it correctly refuses,
then with the flag to produce a real report. The result will be presented
as-is, with the same "hypothesis test only" framing — no profitability
claims, consistent with the project's Development Rules and the Sample
Strategy's own stated purpose.

## Known Limitations

- `summary.json` may contain the non-standard JSON tokens `Infinity`/`-Infinity`
  when `profit_factor` has no losing trades to divide by; Python's own
  `json` module reads this back correctly, but strictly RFC-compliant JSON
  parsers in other languages may reject it. Acceptable for this
  research-platform milestone; revisit if `summary.json` needs to be
  consumed by a strict external JSON parser later.
- The runner does not retry or resume a partially-written run directory —
  if the process is killed mid-export, the run directory may contain fewer
  than three files. Not handled specially in this milestone (no atomic
  multi-file export requirement was specified, unlike the Data Pipeline's
  Parquet+metadata atomicity, which has a stronger correctness need since
  it protects previously-valid persisted data — a report run directory has
  no "previous state" to protect).

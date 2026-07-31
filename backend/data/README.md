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

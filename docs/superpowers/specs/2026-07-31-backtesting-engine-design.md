# Backtesting Engine — Milestone Design

Date: 2026-07-31
Project: Trader v2 — Phase 1
Milestone: Backtesting Engine (single symbol, single timeframe)

## Overview

A sequential, bar-by-bar backtesting engine that simulates trade execution
over a single symbol/timeframe OHLCV series, given a pre-computed stream of
entry signals. It handles position sizing under a capital/margin/risk model,
realistic fill assumptions (next-open entry, gap-through, fees, slippage),
and produces trade history, an equity curve, and standard performance
metrics. The Strategy module (signal generation, e.g. EMA Trend Pullback) is
explicitly out of scope for this milestone — the engine consumes signals as
plain input, making it strategy-agnostic and reusable.

## Goals

- Simulate long and short trades with market entry at the next candle's open.
- Enforce max one open position at a time.
- Apply stop loss and take profit with explicit, documented fill and
  tie-break rules.
- Apply trading fees and slippage to every fill.
- Size positions using a risk-based model that accounts for fees, slippage,
  and a capital/leverage cap, and reject trades that cannot be sized safely.
- Produce trade history, a mark-to-market equity curve, and the required
  metrics (drawdown, win rate, profit factor, expectancy, Sharpe ratio,
  max consecutive losses).
- Prevent look-ahead bias by construction (never read future candles).
- Respect Data Pipeline dataset-quality metadata (`complete`/`incomplete`,
  gaps) without depending on the filesystem directly.

## Non-Goals (excluded from this milestone)

- Strategy/signal generation logic (next milestone).
- Multiple concurrent positions, multiple symbols, or portfolio-level logic.
- Exchange lot-size / minimum-notional rounding rules.
- Realistic margin/liquidation mechanics (funding rates, maintenance margin,
  forced liquidation) — leverage here is a simple buying-power cap, not a
  full margin account simulation.
- Parameter optimization (explicitly forbidden project-wide in Phase 1).
- REST API and Supabase persistence (later milestones).

## Architecture

Per the project's module-separation rule (Data, Strategy, Execution, Risk,
Analytics), this milestone spans three new modules plus a thin loader that
bridges to the Data Pipeline module. Strategy does not exist yet.

```
Trader_v2/
  backend/
    risk/
      __init__.py
      sizing.py         # risk-based position sizing + rejection rules
    engine/
      __init__.py
      models.py          # Signal, Trade, RejectedSignal, DatasetQuality, BacktestConfig, BacktestResult
      loader.py            # Parquet + metadata -> in-memory OHLCV + DatasetQuality (filesystem-aware)
      backtester.py          # the bar-by-bar simulation loop (filesystem-agnostic)
    analytics/
      __init__.py
      metrics.py          # equity curve -> win rate, profit factor, expectancy, Sharpe, drawdown, consecutive losses
    tests/
      risk/
        test_sizing.py
      engine/
        test_loader.py
        test_backtester.py
      analytics/
        test_metrics.py
```

**Dependency direction:** `loader` depends on `data.storage` (Data Pipeline
module) and produces plain in-memory objects. `backtester` depends on
`risk.sizing`, `engine.models`, and `analytics.metrics`, but never on
`data.storage` or `pathlib.Path` — it only ever receives already-loaded
data. This keeps the simulation core fully unit-testable with synthetic
in-memory data and reusable outside a filesystem context (e.g. later, an
API endpoint can load once and run many backtests).

## Domain Models (`engine/models.py`)

```python
@dataclass(frozen=True)
class Signal:
    signal_id: str                 # unique identifier for traceability (e.g. UUID or caller-assigned)
    timestamp: datetime          # the signal (close) bar's timestamp
    direction: str                # "long" | "short"
    stop_loss_price: float
    take_profit_price: float


@dataclass(frozen=True)
class DatasetQuality:
    status: str                    # "complete" | "incomplete"
    gaps: list[GapRange]            # GapRange: start: datetime, end: datetime, severity: str


class BacktestConfig(BaseModel):    # Pydantic
    initial_capital: float          # > 0
    leverage: float = 1.0             # >= 1.0, buying-power multiplier
    risk_per_trade_pct: float          # e.g. 0.005 for 0.5%, > 0
    fee_pct: float                      # e.g. 0.001 for 0.1%, >= 0
    slippage_pct: float                  # e.g. 0.0005, >= 0
    allow_incomplete_dataset: bool = False


@dataclass(frozen=True)
class Trade:
    signal_id: str                  # traces back to the originating Signal
    entry_time: datetime
    entry_price: float            # post-slippage fill price
    exit_time: datetime
    exit_price: float               # post-slippage fill price
    direction: str                   # "long" | "short"
    quantity: float
    stop_loss_price: float
    take_profit_price: float
    exit_reason: str                  # "stop_loss" | "take_profit" | "end_of_data"
    entry_fee: float
    exit_fee: float
    equity_before: float                 # realized equity immediately before this trade opened (== equity_at_entry)
    equity_after: float                    # realized equity immediately after this trade closed
    pnl: float                         # net of fees, in quote currency
    pnl_pct: float                      # pnl / (entry_price * quantity)
    r_multiple: float                    # pnl / (equity_before * risk_per_trade_pct)


@dataclass(frozen=True)
class RejectedSignal:
    signal_id: str
    timestamp: datetime
    reason: str    # "invalid_stop_placement" | "zero_stop_distance" | "invalid_quantity" | "insufficient_capital"


@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig               # the configuration used for this run
    dataset_quality: DatasetQuality        # the dataset-quality info used for this run
    trades: list[Trade]
    rejected_signals: list[RejectedSignal]
    equity_curve: pl.DataFrame     # columns: timestamp, equity
    metrics: BacktestMetrics
```

## Loader (`engine/loader.py`) — filesystem boundary

The **only** module in this milestone allowed to touch `Path` or
`data.storage`. Responsibility: read a dataset's Parquet file and
`{timeframe}.metadata.json` sidecar (via `data.storage.read_parquet_if_exists`
/ `read_metadata_if_exists`), and produce:

```python
def load_dataset(base_dir: Path, exchange: str, symbol_slug: str, timeframe: str) -> tuple[pl.DataFrame, DatasetQuality]
```

`DatasetQuality.status`/`.gaps` are copied directly from the metadata
sidecar's `status`/`gaps` fields. This function does no validation or
simulation logic — it is a thin adapter. Everything downstream
(`backtester.run`) takes the returned `pl.DataFrame` and `DatasetQuality`
as plain arguments and never touches the filesystem again.

## Capital and Margin Model

- `equity` starts at `config.initial_capital` and is updated after every
  realized trade (fees and P&L). Mark-to-market unrealized P&L is used only
  for the equity **curve**, never for sizing the next trade (sizing always
  uses the last **realized** equity — no compounding unrealized gains into
  new risk).
- **Buying power** for a trade is `equity_at_entry * config.leverage`. This
  is a simplified buying-power cap, not a full margin account simulation
  (no maintenance margin, no funding, no liquidation mechanics) — documented
  explicitly as a Known Limitation.
- **Required margin** for a candidate trade is
  `(entry_price_filled * quantity) / config.leverage`, and by construction
  (see sizing below) this is always `<= equity_at_entry`.

## Position Sizing (`risk/sizing.py`)

Goal: size the position so that, if the trade is stopped out, the
**realized** loss (price movement **and** fees **and** slippage on both
legs) is as close as possible to `config.risk_per_trade_pct * equity_at_entry`
— not just the raw price distance.

Given `entry_price_filled` (candle open + entry slippage) and
`signal.stop_loss_price`:

```python
def size_position(
    direction: str,
    entry_price_filled: float,
    stop_loss_price: float,
    equity_at_entry: float,
    config: BacktestConfig,
) -> SizingResult:
    ...
```

1. **Validate stop placement** relative to the *actual* entry fill:
   - Long: `stop_loss_price` must be `< entry_price_filled`.
   - Short: `stop_loss_price` must be `> entry_price_filled`.
   - Violation -> reject with `"invalid_stop_placement"`.
2. **Compute the stop's exit fill price**, applying exit slippage in the
   adverse direction (a long's stop is a sell -> slips lower; a short's
   stop is a buy -> slips higher):
   - Long: `stop_exit_price = stop_loss_price * (1 - slippage_pct)`
   - Short: `stop_exit_price = stop_loss_price * (1 + slippage_pct)`
3. **Price risk per unit** = `abs(entry_price_filled - stop_exit_price)`.
   If this is `<= 0` -> reject with `"zero_stop_distance"`.
4. **Fee cost per unit** = `fee_pct * (entry_price_filled + stop_exit_price)`
   (entry fee + exit fee, each proportional to that leg's notional per unit).
5. **Effective risk per unit** = price risk per unit + fee cost per unit.
6. **Risk-based quantity** = `(equity_at_entry * risk_per_trade_pct) / effective_risk_per_unit`.
   If this is `<= 0` or non-finite -> reject with `"invalid_quantity"`.
7. **Capital-capped quantity** = `(equity_at_entry * leverage) / entry_price_filled`.
   If this is `<= 0` (e.g. `equity_at_entry <= 0`) -> reject with
   `"insufficient_capital"`.
8. **Final quantity** = `min(risk_based_quantity, capital_capped_quantity)`.
   If the capital cap binds, the trade's realized worst-case loss will be
   *less* than the configured risk % (safe direction) — this is not a
   rejection condition, only a reduced-size trade.
9. If final quantity is `<= 0` (degenerate) -> reject with
   `"invalid_quantity"`.

A `Trade`'s `r_multiple` (`pnl / (equity_before * risk_per_trade_pct)`, where
`equity_before` is that trade's `equity_at_entry`)
is expected to be approximately `-1.0` for trades that exit at the stop —
this is the concrete, testable expression of "worst-case loss at the stop
matches the configured risk per trade."

## Entry-Candle Processing (explicit order)

When the engine is flat and a signal scheduled for "enter at this candle's
open" exists, processing for that candle proceeds in this exact order:

1. **Fill at the open**: `raw_fill = candle.open`; apply entry slippage
   adverse to the trader -> `entry_price_filled` (long: `raw_fill * (1 + slippage_pct)`;
   short: `raw_fill * (1 - slippage_pct)`).
2. **Validate and size** the position per "Position Sizing" above, using
   `entry_price_filled`. If any rejection rule fires, append a
   `RejectedSignal` with the reason, open **no** position, and move on —
   this candle is otherwise treated as a normal flat candle (no entry, no
   exit).
3. **Accept**: deduct the entry fee (`entry_price_filled * quantity * fee_pct`)
   from equity, open a `Position` (entry_time = this candle's timestamp,
   entry_price = `entry_price_filled`, quantity, direction,
   `stop_loss_price`, `take_profit_price` from the signal).
4. **Gap-through-at-open check**: compare `entry_price_filled` itself
   against `take_profit_price` (the stop was already validated as not
   gapped-through in step 2 — an invalid stop rejects the whole trade
   rather than producing an instant same-bar stop-out). If the fill has
   already reached or passed the take-profit level in the trade's favor,
   exit immediately at `entry_price_filled` with `exit_reason = "take_profit"`
   — this is a same-bar entry-and-exit trade.
5. **Otherwise, evaluate the rest of this candle's range**: check whether
   `[candle.low, candle.high]` touches `stop_loss_price` and/or
   `take_profit_price`.
   - Both touched -> exit at `stop_loss_price` (conservative tie-break;
     see "Same-Bar SL/TP Conflict" below), `exit_reason = "stop_loss"`.
   - Only SL touched -> exit at `stop_loss_price`, `exit_reason = "stop_loss"`.
   - Only TP touched -> exit at `take_profit_price`, `exit_reason = "take_profit"`.
   - Neither touched -> position remains open into the next candle.
6. If an exit occurred in steps 4–5, apply exit slippage and the exit fee,
   compute `pnl`/`pnl_pct`/`r_multiple`, realize the P&L into equity, and
   record the `Trade`. **No new entry may occur on this same candle** (see
   "Same-Candle Exit/Re-entry Prohibition").

## Subsequent-Candle Processing (position already open from an earlier candle)

For each candle while a position is open (carried over from a prior
candle), before anything else is considered for that candle:

1. **Gap-through-at-open check**: if `candle.open` has already passed
   `stop_loss_price` and/or `take_profit_price` in the adverse/favorable
   direction (a real gap between candles, not a slow intrabar move), the
   exit fills at `candle.open` (adjusted for slippage) rather than at the
   stale SL/TP level — this reflects how a real stop/limit order behaves
   when price gaps through it. If both levels were gapped through
   simultaneously, the stop-loss-first tie-break still applies.
2. **Otherwise, evaluate `[candle.low, candle.high]`** exactly as in step 5
   of "Entry-Candle Processing" (both-touched -> stop first; single-sided
   touch -> that exit).
3. If neither gapped-through nor touched, the position remains open; the
   equity curve for this candle is marked to market using `candle.close`.

## Same-Bar SL/TP Conflict

Whenever both the stop-loss and take-profit levels fall within a single
candle's evaluation (whether via the high/low range or a simultaneous
gap-through at open), the engine **always assumes the stop loss triggers
first**. OHLC data cannot reveal the true intrabar price path, so this is a
deliberate, conservative, and consistently-applied assumption — not an
attempt to guess favorably. It is documented here and enforced identically
in both entry-candle and subsequent-candle processing.

## Same-Candle Exit/Re-entry Prohibition

A new position may be entered **no earlier than the next candle's open**
after any exit, even if that exit itself occurred at the very start (open)
of a candle. The engine enforces this structurally rather than with a
special-case flag: **each candle's processing is mutually exclusive between
"manage an existing open position" and "consider a new entry."** If a
position is open at the start of a candle, that candle only ever runs
"Subsequent-Candle Processing" (which may produce an exit) — a new entry is
never considered on that same candle, regardless of the outcome. A new
entry is only considered on a candle where the engine started the candle
already flat.

## Fees and Slippage — summary

| Event | Slippage | Fee |
|---|---|---|
| Entry (market, at next-candle open) | Adverse: long pays more, short receives less | `fee_pct * entry_price_filled * quantity` |
| Stop-loss exit | Adverse: long's sell slips down, short's buy-to-cover slips up | `fee_pct * exit_price * quantity` |
| Take-profit exit | Adverse, same direction convention as stop-loss exit | `fee_pct * exit_price * quantity` |
| Gap-through exit (open-based) | Already reflected in the gapped price itself; the same adverse slippage adjustment is still applied on top | `fee_pct * exit_price * quantity` |
| End-of-data forced close (see below) | Same adverse convention, using the final candle's close as the reference price | `fee_pct * exit_price * quantity` |

If a position is still open when the data ends, it is force-closed at the
last candle's `close` price (adjusted for exit slippage and fee),
`exit_reason = "end_of_data"`.

## Look-Ahead Bias Prevention

1. The engine consumes `Signal` objects as pre-computed input — it never
   computes indicators or derives entries from data itself. By contract, a
   signal timestamped at candle `N` is only actionable at candle `N+1`'s
   open; the engine does not inspect any candle beyond the one it is
   currently processing to make that decision.
2. The simulation loop advances candle-by-candle in strict chronological
   order using only: the current candle's OHLC, the current open
   position's state (if any), and already-realized equity. No vectorized
   shortcut or pre-scan of the full series is used for fill decisions.
3. Position sizing uses only `equity_at_entry` (realized equity as of the
   start of the entry candle) and the signal's own stop/take-profit levels
   — never any later candle.
4. **Regression test**: run a backtest, record all trades and the equity
   curve up to and including the last real trade's exit; then run again
   with every candle *after* that exit mutated to extreme/adversarial OHLCV
   values; assert the trades and equity curve up to that point are
   byte-identical. This is the concrete, automated check that future data
   cannot influence past results.

## Incomplete Dataset and Gap Handling

- Before simulating, the engine checks `DatasetQuality.status`. If
  `"incomplete"` and `config.allow_incomplete_dataset` is `False` (the
  default), the engine raises a clear error and does not run — matching the
  Data Pipeline's design principle that it only *reports* dataset quality;
  the *consumer* (this engine) decides what's acceptable.
- If running is allowed (either `status == "complete"`, or `"incomplete"`
  with the flag set), the engine additionally checks whether any gap in
  `DatasetQuality.gaps` overlaps the OHLCV series' actual date range being
  simulated, and logs a warning naming each overlapping gap's range and
  severity so results carry that caveat.
- The engine never fabricates missing candles. It simply advances through
  whatever candles physically exist in the provided DataFrame, in order. A
  position that was open going into a gap is evaluated against the next
  *available* candle after the gap using the same gap-through-at-open rule
  described above — this is an approximation of real execution during the
  missing period and is called out explicitly as a Known Limitation.

## Metrics (`analytics/metrics.py`)

All computed from `trades` and the mark-to-market `equity_curve`:

- **Win Rate** = winning trades / total trades (`pnl > 0` counts as a win).
  With zero trades, all metrics are `None` (there is nothing to report).
- **Profit Factor** = gross profit / `abs(gross loss)` (sum of positive
  `pnl` / absolute sum of negative `pnl`). If there are losing trades but
  `gross loss == 0` is impossible by definition; if there are **no**
  losing trades, Profit Factor is reported as `inf` (undefined upside,
  not an error).
- **Expectancy** = mean(`pnl`) across all trades.
- **Sharpe Ratio** = `mean(r) / std(r) * sqrt(candles_per_year)`, where `r`
  is the series of per-candle simple returns of the equity curve
  (`equity[i] / equity[i-1] - 1`), and `candles_per_year` is derived from
  the timeframe (e.g. 15m -> `365 * 24 * 4 = 35040`). Risk-free rate is
  assumed to be `0` (documented simplification). If `std(r) == 0` (e.g. no
  trades ever executed, so equity never moves), Sharpe is reported as `0.0`
  rather than raising a division error.
- **Max Drawdown** = max peak-to-trough percentage decline of the equity
  curve: `max((peak - equity) / peak)` over the series.
- **Max Consecutive Losses** = longest streak of consecutive trades (in
  trade sequence order, not calendar time) with `pnl <= 0`.

## Testing Strategy

All tests use synthetic, hand-computed OHLCV/signal data — no dependency on
the Data Pipeline's real Binance data.

- **`test_sizing.py`**: each rejection rule in isolation (invalid stop
  placement for long/short, zero stop distance, degenerate/negative
  quantity, insufficient capital); a valid case verified against a
  hand-computed expected quantity; a capital-cap-binds case; and a
  hand-computed case confirming `r_multiple ≈ -1.0` when a sized trade is
  later stopped out (ties sizing directly to the risk-per-trade guarantee).
- **`test_loader.py`**: reads a Parquet + metadata sidecar written via
  `data.storage` into a `tmp_path`, confirms the returned `DatasetQuality`
  matches the sidecar's `status`/`gaps`. This is the only test file in this
  milestone that touches the filesystem.
- **`test_backtester.py`**:
  - Long and short trades filling at next-candle open with slippage.
  - Take-profit hit, stop-loss hit, both-touched-in-one-candle (stop wins),
    on both entry candles and later candles.
  - Gap-through-at-open exit (price gaps past SL/TP between candles) fills
    at the gapped price, not the stale level.
  - Stop invalid relative to actual entry fill -> trade rejected, recorded
    in `rejected_signals`, no position opened.
  - Same-candle exit-then-signal does **not** produce a same-candle
    re-entry; the next entry (if any) only fills at the following candle's
    open.
  - Position open at end of data force-closes at the final close price.
  - `allow_incomplete_dataset` gating: `status="incomplete"` without the
    flag raises; with the flag, runs and logs the overlapping gap warning.
  - Look-ahead regression test as described above.
  - End-to-end: a small (10-20 candle) fully hand-computed synthetic
    series/signal set with expected trades, equity curve, and every metric
    value computed by hand and asserted exactly.
- **`test_metrics.py`**: each metric formula against hand-computed trade
  lists / equity curves, including edge cases (zero losing trades ->
  profit factor undefined/`inf` handling, single trade, all-losing streak).

## Known Limitations

- Leverage models buying-power capacity only; no margin/liquidation/funding
  mechanics.
- No exchange lot-size or minimum-notional rounding.
- A position carried across a data gap is evaluated against the next
  available candle using the gap-through rule — this approximates, but does
  not exactly reproduce, execution during the missing period.
- Sharpe ratio uses per-candle (not per-trade) returns with a 0% risk-free
  rate; this is a simplification appropriate for research/comparison
  purposes, not a regulatory-grade risk metric.

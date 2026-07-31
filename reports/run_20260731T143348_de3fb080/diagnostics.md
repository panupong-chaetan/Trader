# Strategy Diagnostics — EMA Trend Pullback (BTC/USDT, 15m)

Analysis of run `run_20260731T143348_de3fb080` (2020-01-01 → 2026-07-31,
dataset `status: incomplete`, `--allow-incomplete-dataset` used).
Read-only analysis over `summary.json` / `trades.csv` / `equity_curve.parquet`,
plus a read-only re-derivation of the strategy's raw signal list for the
skipped-signal breakdown. **No strategy or engine parameters were changed
or optimized.**

## Executive Summary

The strategy loses money **consistently across every year and every month
of the dataset**, in both bull and bear price regimes alike. Two distinct,
independent problems compound the loss:

1. **Negative edge before costs.** Gross PnL (before any fees) is
   **−$2,836**, already a loss. The nominal win/reward setup (33% win rate,
   2R target) is only marginally profitable in theory (`0.33×2 − 0.67×1 ≈
   −0.01`) — and in practice the *realized* average R-multiple on
   take-profit exits is only **+0.88R, not +2.0R** (see Finding 4), pushing
   true expectancy to roughly **−0.38R per trade**.
2. **Fees more than triple the damage.** Total fees paid were **$7,164** —
   **253% of the gross loss**. At 7,183 trades over 6.5 years (roughly one
   trade every 9.6 hours), transaction costs alone are large enough to turn
   a marginal setup into a near-total wipeout (final equity: **$0.019**,
   from a **$10,000** start).

Neither problem is regime-specific — see Finding 8.

---

## 1. Performance by Year

Raw dollar PnL is heavily distorted by compounding (early years hold most
of the capital), so both dollar PnL and **compounding-adjusted % return**
are shown. The % return is the honest year-by-year picture.

| Year | Trades | Win Rate | Net PnL ($) | Compounding Return (%) |
|---|---|---|---|---|
| 2020 | 1,020 | 33.6% | −8,245.20 | **−82.5%** |
| 2021 | 1,138 | 32.8% | −1,379.23 | **−78.6%** |
| 2022 | 1,059 | 35.2% | −298.70 | **−79.5%** |
| 2023 | 1,023 | 31.8% | −69.00 | **−89.8%** |
| 2024 | 1,083 | 34.9% | −6.69 | **−85.0%** |
| 2025 | 1,162 | 31.2% | −1.09 | **−92.8%** |
| 2026 (partial) | 698 | 32.4% | −0.07 | **−77.4%** |

**Finding 1:** Every single year loses **77–93% of that year's starting
capital**, regardless of dollar magnitude. The dollar-PnL column alone
would misleadingly suggest 2020 is uniquely bad and later years are
"fine" — that's an artifact of equity already being near zero; the
compounding-return column shows the loss rate is essentially constant.

## 2. Performance by Month

79 months total. **0 of 79 months were net-profitable.**

Worst 5 months (dollar terms, dominated by early-2020 when equity was
largest):

| Month | Trades | Win Rate | Net PnL ($) | Fees ($) |
|---|---|---|---|---|
| 2020-05 | 94 | 27.7% | −1,342.96 | 624.15 |
| 2020-02 | 82 | 36.6% | −1,033.30 | 836.34 |
| 2020-06 | 77 | 29.9% | −1,021.98 | 575.68 |
| 2020-07 | 89 | 32.6% | −925.20 | 634.93 |
| 2020-08 | 98 | 28.6% | −876.84 | 455.72 |

**Finding 2:** Zero profitable months out of 79 is a stronger signal than
any single year's number — this is not a few bad months dragging down an
otherwise sound strategy.

## 3. Long vs Short

| Direction | Trades | Win Rate | Net PnL ($) | Avg PnL/Trade ($) |
|---|---|---|---|---|
| Long | 3,760 | 33.5% | −6,071.01 | −1.61 |
| Short | 3,423 | 32.8% | −3,928.97 | −1.15 |

**Finding 3:** Both directions lose, with similar win rates (33.5% vs
32.8%) and similar per-trade averages. There is no meaningful long/short
asymmetry — this rules out "the trend filter only works one direction" as
an explanation.

## 4. Stop-Loss vs Take-Profit Exits

| Exit Reason | Trades | Net PnL ($) | Avg PnL ($) | Avg R-Multiple |
|---|---|---|---|---|
| Stop Loss | 4,760 | −22,280.36 | −4.68 | **−0.997** |
| Take Profit | 2,423 | +12,280.38 | +5.07 | **+0.878** |

**Finding 4 (the key mechanical finding):** Stop-loss exits realize almost
exactly **−1.0R**, confirming the Backtesting Engine's fee/slippage-aware
position sizing works exactly as designed (this matches the earlier
Backtesting Engine milestone's own verification). But take-profit exits
only realize **+0.88R on average — not the nominal +2.0R** the strategy
targets. This happens because position size is computed from
`risked_amount / (price_risk_per_unit + fee_cost_per_unit)` — the
fee-inclusive denominator shrinks the position below what a pure
price-distance calculation would give, so even a full 2R price move
delivers well under 2R in realized dollars once that smaller position's
own take-profit-side fees are subtracted. The stop side is fee-protected
by design; the profit side is not protected the same way and is
structurally diluted. With a 33% win rate, +0.88R wins are not nearly
enough to offset −1.0R losses (`0.33×0.88 − 0.67×1.0 ≈ −0.38R` per trade).

## 5. Trade Duration

| Statistic | Value |
|---|---|
| Mean | 218.8 minutes (~14.6 candles) |
| Median | 120 minutes (8 candles) |
| Min | 0 minutes (same-candle entry+exit, gap-through or immediate TP at open) |
| Max | 6,090 minutes (~4.2 days) |

**Finding 5:** Trades are short — half close within 2 hours. This is
consistent with a mean-reversion-style pullback entry against a fast
EMA(20), which either resolves quickly or gets stopped out quickly.

## 6. Fee Impact / Gross vs Net PnL

| Metric | Value |
|---|---|
| Gross PnL (before fees) | **−$2,836.03** |
| Total fees paid | **$7,163.95** |
| Net PnL (after fees) | **−$9,999.98** |
| Fees as % of gross loss | **252.6%** |

**Finding 6:** The strategy has a negative edge even before costs
(gross PnL is already negative), and fees more than triple the total
damage. Both the edge problem (Finding 4) and the cost problem
(trade frequency × fee rate) need to be addressed for this setup to have
any chance of being viable — fixing only one would not be sufficient.

## 7. Consecutive-Loss Distribution

| Streak Length | Occurrences |
|---|---|
| 1 | 495 |
| 2 | 357 |
| 3 | 264 |
| 4 | 168 |
| 5 | 110 |
| 6 | 65 |
| 7 | 45 |
| 8 | 27 |
| 9 | 29 |
| 10 | 9 |
| 11 | 7 |
| 12 | 7 |
| 13 | 4 |
| 14–15 | 2 each |
| 16 | 1 |
| **21 (worst)** | **1** |

**Finding 7:** A 21-trade losing streak occurred at least once. At a fixed
0.5% risk per trade, a 21-trade streak alone would compound to roughly
`(1-0.005)^21 ≈ 0.90`, a ~10% equity hit from one streak — survivable in
isolation, but streaks this long recurring across thousands of trades with
a −0.38R average expectancy compound into the total collapse seen in the
equity curve.

## 8. Drawdown Periods

The equity curve has effectively **one continuous drawdown** from mid-January
2020 onward, never recovering:

| Peak Time | Peak Equity | Trough Time | Trough Equity | Drawdown % |
|---|---|---|---|---|
| 2020-01-15 00:15 | $10,181.36 | 2026-07-31 06:45 | $0.019 | **99.9998%** (no recovery) |

Four much smaller (0.1–2.8%), fully-recovered drawdowns occurred in the
first two weeks of trading before the equity peak was set — normal
short-term noise, not structurally significant.

**Finding 8:** There is no "regime" to point to for the drawdown — it is
one long, slow bleed with no recovery, consistent with a small negative
per-trade expectancy compounding over thousands of trades rather than a
handful of catastrophic events.

## 9. Signal Frequency and Skipped Signals

| Metric | Value |
|---|---|
| Total signals generated | 16,374 |
| Executed as trades | 7,183 |
| Rejected by sizing (invalid stop, etc.) | 0 |
| **Skipped — position already open** | **9,191 (56.1%)** |

**Finding 9:** More than half of all raw signals are never actionable
because a position from a previous signal is still open (max-one-position
is enforced by the engine, as designed). Average signal spacing is ~14
candles (230,584 candles / 16,374 signals), close to the median 8-candle
trade duration — so overlap, and therefore a high skip rate, is expected
given this strategy's signal frequency relative to its typical hold time.
This is documented engine behavior, not an error, but it does mean the
strategy as specified generates roughly 2.3x more raw signals than it
can ever act on.

## 10. Performance Near Known Dataset Gaps

| Metric | Value |
|---|---|
| Overall average PnL per trade | **−$1.39** |
| Average PnL per trade within ±3 days of any of the 15 known gaps (260 trades) | **−$5.06** |

**Finding 10:** Trades near dataset gaps lose **~3.6x** the average trade.
This is consistent with the engine's documented gap-through-at-open fill
behavior (a stop/take-profit level is skipped past at the actual gapped
price rather than the theoretical level) rather than a strategy defect —
but it does mean the ~15 known gaps contribute a disproportionate,
identifiable share of the total loss, concentrated in a small number of
trades.

## 11. Market Regime Concentration

| Year | BTC Price Change | Strategy Compounding Return |
|---|---|---|
| 2020 | **+302.8%** (strong bull) | −82.5% |
| 2021 | +60.7% (bull) | −78.6% |
| 2022 | **−64.3%** (bear) | −79.5% |
| 2023 | +155.9% (bull) | −89.8% |
| 2024 | +120.2% (bull) | −85.0% |
| 2025 | −6.4% (mild bear) | −92.8% |
| 2026 (partial) | −27.3% (bear) | −77.4% |

**Finding 11 (answers the regime question directly):** Losses are **not**
concentrated in any specific market regime. The strategy loses at a
strikingly similar rate (77–93%) whether BTC is up 303% (2020), down 64%
(2022), or anything in between. This is strong evidence the losses are
**structural** (Findings 4 and 6 — realized R-multiple asymmetry and fee
drag) rather than caused by the strategy being mismatched to a particular
kind of market.

---

## Bottom Line

This is a hypothesis test result, not a profitability claim, exactly as
framed in the original backtest report. The diagnostics point to two
specific, well-evidenced mechanisms — a take-profit R-multiple that
realizes less than half its nominal target (Finding 4), and fee drag from
high trade frequency that more than triples an already-negative gross edge
(Finding 6) — operating consistently across every year, every month, both
trade directions, and every market regime tested (Finding 11). No
parameter was changed or optimized to produce this analysis.

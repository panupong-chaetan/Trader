# analytics — Performance Metrics

`metrics.py`'s `compute_metrics(trades, equity_curve, candles_per_year)`
returns win rate, profit factor, expectancy, Sharpe ratio, max drawdown,
and max consecutive losses.

- Zero trades -> every metric is `None`.
- No losing trades -> profit factor is `inf`.
- No equity variance -> Sharpe ratio is `0.0`.
- Sharpe uses per-candle equity returns, annualized by `candles_per_year`
  (inferred by the engine from the OHLCV series' own interval — not a
  config field), with a 0% risk-free rate.

See `docs/superpowers/specs/2026-07-31-backtesting-engine-design.md` for
exact formulas.

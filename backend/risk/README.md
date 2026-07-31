# risk — Position Sizing

`sizing.py` computes trade quantity from a risk-per-trade percentage, the
actual entry fill price, and the signal's stop-loss price — accounting for
fees and slippage on both legs so that the realized worst-case loss at the
stop is as close as possible to `config.risk_per_trade_pct * equity_at_entry`,
then caps the result by available capital and leverage.

## Rejection reasons

- `invalid_stop_placement` — the stop is on the wrong side of the entry fill.
- `zero_stop_distance` — the stop equals the entry fill exactly.
- `insufficient_capital` — equity at entry is `<= 0`.
- `invalid_quantity` — defensive guard for non-finite/non-positive results;
  not expected to trigger under validated config + positive equity.

See `docs/superpowers/specs/2026-07-31-backtesting-engine-design.md` for
the full formula derivation.

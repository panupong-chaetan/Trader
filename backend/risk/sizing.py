from __future__ import annotations

import math
from dataclasses import dataclass

from engine.models import BacktestConfig


@dataclass(frozen=True)
class SizingResult:
    accepted: bool
    quantity: float | None = None
    reason: str | None = None


def size_position(
    direction: str,
    entry_price_filled: float,
    stop_loss_price: float,
    equity_at_entry: float,
    config: BacktestConfig,
) -> SizingResult:
    if equity_at_entry <= 0:
        return SizingResult(accepted=False, reason="insufficient_capital")

    if direction == "long":
        if stop_loss_price > entry_price_filled:
            return SizingResult(accepted=False, reason="invalid_stop_placement")
        if stop_loss_price == entry_price_filled:
            return SizingResult(accepted=False, reason="zero_stop_distance")
        stop_exit_price = stop_loss_price * (1 - config.slippage_pct)
    else:
        if stop_loss_price < entry_price_filled:
            return SizingResult(accepted=False, reason="invalid_stop_placement")
        if stop_loss_price == entry_price_filled:
            return SizingResult(accepted=False, reason="zero_stop_distance")
        stop_exit_price = stop_loss_price * (1 + config.slippage_pct)

    price_risk_per_unit = abs(entry_price_filled - stop_exit_price)
    fee_cost_per_unit = config.fee_pct * (entry_price_filled + stop_exit_price)
    effective_risk_per_unit = price_risk_per_unit + fee_cost_per_unit

    risk_based_quantity = (equity_at_entry * config.risk_per_trade_pct) / effective_risk_per_unit
    capital_capped_quantity = (equity_at_entry * config.leverage) / entry_price_filled
    quantity = min(risk_based_quantity, capital_capped_quantity)

    if not math.isfinite(quantity) or quantity <= 0:
        return SizingResult(accepted=False, reason="invalid_quantity")

    return SizingResult(accepted=True, quantity=quantity)

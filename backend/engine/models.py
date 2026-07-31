from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl
from pydantic import BaseModel, field_validator


@dataclass(frozen=True)
class Signal:
    signal_id: str
    timestamp: datetime
    direction: str  # "long" | "short"
    stop_loss_price: float
    take_profit_price: float


@dataclass(frozen=True)
class GapRange:
    start: datetime
    end: datetime
    severity: str


@dataclass(frozen=True)
class DatasetQuality:
    status: str  # "complete" | "incomplete"
    gaps: list[GapRange]


class BacktestConfig(BaseModel):
    initial_capital: float
    leverage: float = 1.0
    risk_per_trade_pct: float
    fee_pct: float
    slippage_pct: float
    allow_incomplete_dataset: bool = False

    @field_validator("initial_capital", "risk_per_trade_pct")
    @classmethod
    def _must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    @field_validator("leverage")
    @classmethod
    def _leverage_at_least_one(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("must be >= 1.0")
        return value

    @field_validator("fee_pct", "slippage_pct")
    @classmethod
    def _must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must be >= 0")
        return value


@dataclass(frozen=True)
class Trade:
    signal_id: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    direction: str  # "long" | "short"
    quantity: float
    stop_loss_price: float
    take_profit_price: float
    exit_reason: str  # "stop_loss" | "take_profit" | "end_of_data"
    entry_fee: float
    exit_fee: float
    equity_before: float
    equity_after: float
    pnl: float
    pnl_pct: float
    r_multiple: float


@dataclass(frozen=True)
class RejectedSignal:
    signal_id: str
    timestamp: datetime
    reason: str  # "invalid_stop_placement" | "zero_stop_distance" | "invalid_quantity" | "insufficient_capital"


@dataclass(frozen=True)
class BacktestMetrics:
    total_trades: int
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    max_consecutive_losses: int | None


@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig
    dataset_quality: DatasetQuality
    trades: list[Trade]
    rejected_signals: list[RejectedSignal]
    equity_curve: pl.DataFrame
    metrics: BacktestMetrics

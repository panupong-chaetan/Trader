from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrategyCatalogRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str
    strategy_name: str
    category: str
    hypothesis: str
    market: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    total_signals: int
    total_trades: int
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_return: float
    total_fees: float
    rejected_signals: int
    report_directory: str
    created_at: datetime

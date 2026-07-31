from __future__ import annotations

import polars as pl

from research.models import StrategyCatalogRecord

_SCHEMA = {
    "strategy_name": pl.Utf8,
    "category": pl.Utf8,
    "profit_factor": pl.Float64,
    "sharpe_ratio": pl.Float64,
    "expectancy": pl.Float64,
    "max_drawdown": pl.Float64,
    "total_trades": pl.Int64,
    "total_return": pl.Float64,
}


def compare_strategies(records: list[StrategyCatalogRecord]) -> pl.DataFrame:
    ordered = sorted(records, key=lambda record: record.created_at)
    rows = [
        {
            "strategy_name": record.strategy_name,
            "category": record.category,
            "profit_factor": record.profit_factor,
            "sharpe_ratio": record.sharpe_ratio,
            "expectancy": record.expectancy,
            "max_drawdown": record.max_drawdown,
            "total_trades": record.total_trades,
            "total_return": record.total_return,
        }
        for record in ordered
    ]
    return pl.DataFrame(rows, schema=_SCHEMA)

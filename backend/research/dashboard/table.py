from __future__ import annotations

import polars as pl

from research.models import StrategyCatalogRecord

_SCHEMA = {
    "Strategy": pl.Utf8,
    "Category": pl.Utf8,
    "Hypothesis": pl.Utf8,
    "Market": pl.Utf8,
    "Timeframe": pl.Utf8,
    "Profit Factor": pl.Float64,
    "Sharpe": pl.Float64,
    "Expectancy": pl.Float64,
    "Win Rate": pl.Float64,
    "Max Drawdown": pl.Float64,
    "Total Return": pl.Float64,
    "Trades": pl.Int64,
    "Fees": pl.Float64,
    "Created At": pl.Datetime,
}


def build_dashboard_table(records: list[StrategyCatalogRecord]) -> pl.DataFrame:
    rows = [
        {
            "Strategy": record.strategy_name,
            "Category": record.category,
            "Hypothesis": record.hypothesis,
            "Market": record.market,
            "Timeframe": record.timeframe,
            "Profit Factor": record.profit_factor,
            "Sharpe": record.sharpe_ratio,
            "Expectancy": record.expectancy,
            "Win Rate": record.win_rate,
            "Max Drawdown": record.max_drawdown,
            "Total Return": record.total_return,
            "Trades": record.total_trades,
            "Fees": record.total_fees,
            "Created At": record.created_at,
        }
        for record in records
    ]
    return pl.DataFrame(rows, schema=_SCHEMA)

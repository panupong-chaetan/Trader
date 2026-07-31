from __future__ import annotations

from datetime import datetime, timezone

from research.dashboard.table import build_dashboard_table
from research.models import StrategyCatalogRecord

_COLUMNS = [
    "Strategy", "Category", "Hypothesis", "Market", "Timeframe",
    "Profit Factor", "Sharpe", "Expectancy", "Win Rate", "Max Drawdown",
    "Total Return", "Trades", "Fees", "Created At",
]


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="trend_following",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=10,
        total_trades=8,
        win_rate=0.5,
        profit_factor=1.4,
        expectancy=5.0,
        sharpe_ratio=0.8,
        max_drawdown=0.1,
        total_return=4.2,
        total_fees=20.0,
        rejected_signals=2,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return StrategyCatalogRecord(**base)


def test_build_dashboard_table_returns_expected_columns_in_order() -> None:
    df = build_dashboard_table([_record()])

    assert df.columns == _COLUMNS


def test_build_dashboard_table_maps_values_correctly() -> None:
    record = _record()

    df = build_dashboard_table([record])

    row = df.row(0, named=True)
    assert row["Strategy"] == record.strategy_name
    assert row["Category"] == record.category
    assert row["Hypothesis"] == record.hypothesis
    assert row["Market"] == record.market
    assert row["Timeframe"] == record.timeframe
    assert row["Profit Factor"] == record.profit_factor
    assert row["Sharpe"] == record.sharpe_ratio
    assert row["Expectancy"] == record.expectancy
    assert row["Win Rate"] == record.win_rate
    assert row["Max Drawdown"] == record.max_drawdown
    assert row["Total Return"] == record.total_return
    assert row["Trades"] == record.total_trades
    assert row["Fees"] == record.total_fees


def test_build_dashboard_table_handles_empty_list() -> None:
    df = build_dashboard_table([])

    assert df.columns == _COLUMNS
    assert df.is_empty()

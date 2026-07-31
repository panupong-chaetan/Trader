from __future__ import annotations

from datetime import datetime, timezone

from research.comparison import compare_strategies
from research.models import StrategyCatalogRecord

_COLUMNS = [
    "strategy_name",
    "category",
    "profit_factor",
    "sharpe_ratio",
    "expectancy",
    "max_drawdown",
    "total_trades",
    "total_return",
]


def _record(**overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="breakout",
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


def test_compare_strategies_returns_expected_columns_in_order() -> None:
    df = compare_strategies([_record()])

    assert df.columns == _COLUMNS


def test_compare_strategies_orders_by_created_at_not_performance() -> None:
    better_but_older = _record(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        profit_factor=5.0,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    worse_but_newer = _record(
        experiment_id="strat_b_20260201T000000_22222222",
        strategy_name="strat_b",
        profit_factor=1.0,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    df = compare_strategies([worse_but_newer, better_but_older])

    assert df["strategy_name"].to_list() == ["strat_a", "strat_b"]


def test_compare_strategies_preserves_none_metrics() -> None:
    record = _record(profit_factor=None, sharpe_ratio=None, expectancy=None, max_drawdown=None)

    df = compare_strategies([record])

    assert df["profit_factor"].to_list() == [None]
    assert df["sharpe_ratio"].to_list() == [None]
    assert df["expectancy"].to_list() == [None]
    assert df["max_drawdown"].to_list() == [None]


def test_compare_strategies_handles_empty_list() -> None:
    df = compare_strategies([])

    assert df.columns == _COLUMNS
    assert df.is_empty()

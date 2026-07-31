from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research.dashboard.sorting import SORT_FIELDS, sort_records
from research.models import StrategyCatalogRecord


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


def test_sort_records_defaults_to_created_at_descending() -> None:
    older = _record(experiment_id="a", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _record(experiment_id="b", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))

    result = sort_records([older, newer], sort_key=None)

    assert [r.experiment_id for r in result] == ["b", "a"]


def test_sort_records_by_profit_factor_descending() -> None:
    low = _record(experiment_id="a", profit_factor=1.0)
    high = _record(experiment_id="b", profit_factor=2.0)

    result = sort_records([low, high], sort_key="profit_factor")

    assert [r.experiment_id for r in result] == ["b", "a"]


def test_sort_records_ascending_when_requested() -> None:
    low = _record(experiment_id="a", profit_factor=1.0)
    high = _record(experiment_id="b", profit_factor=2.0)

    result = sort_records([high, low], sort_key="profit_factor", descending=False)

    assert [r.experiment_id for r in result] == ["a", "b"]


def test_sort_records_places_none_values_last_in_both_directions() -> None:
    has_value = _record(experiment_id="a", sharpe_ratio=1.0)
    no_value = _record(experiment_id="b", sharpe_ratio=None)

    desc = sort_records([no_value, has_value], sort_key="sharpe", descending=True)
    asc = sort_records([no_value, has_value], sort_key="sharpe", descending=False)

    assert [r.experiment_id for r in desc] == ["a", "b"]
    assert [r.experiment_id for r in asc] == ["a", "b"]


def test_sort_records_raises_on_unknown_key() -> None:
    with pytest.raises(ValueError):
        sort_records([_record()], sort_key="not_a_real_metric")


def test_sort_fields_covers_expected_metrics() -> None:
    assert set(SORT_FIELDS) == {
        "profit_factor", "sharpe", "expectancy", "win_rate", "max_drawdown",
        "total_return", "trades", "fees", "created_at", "strategy", "category",
    }

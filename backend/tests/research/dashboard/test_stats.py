from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research.dashboard.stats import compute_summary_stats
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


def test_compute_summary_stats_counts_and_averages() -> None:
    records = [
        _record(experiment_id="a", profit_factor=1.0, sharpe_ratio=0.5, max_drawdown=0.1),
        _record(experiment_id="b", profit_factor=3.0, sharpe_ratio=1.5, max_drawdown=0.3),
    ]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.total_experiments == 2
    assert stats.avg_profit_factor == pytest.approx(2.0)
    assert stats.avg_sharpe == pytest.approx(1.0)
    assert stats.avg_max_drawdown == pytest.approx(0.2)


def test_compute_summary_stats_averages_skip_none_values() -> None:
    records = [
        _record(experiment_id="a", profit_factor=2.0),
        _record(experiment_id="b", profit_factor=None),
    ]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.avg_profit_factor == pytest.approx(2.0)


def test_compute_summary_stats_averages_are_none_when_all_null() -> None:
    records = [_record(profit_factor=None, sharpe_ratio=None, max_drawdown=None)]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.avg_profit_factor is None
    assert stats.avg_sharpe is None
    assert stats.avg_max_drawdown is None


def test_compute_summary_stats_best_experiment_is_none_without_explicit_metric() -> None:
    records = [_record(profit_factor=99.0)]

    stats = compute_summary_stats(records, best_metric=None)

    assert stats.best_experiment is None
    assert stats.best_experiment_metric is None


def test_compute_summary_stats_best_experiment_uses_given_metric() -> None:
    low = _record(experiment_id="a", profit_factor=1.0)
    high = _record(experiment_id="b", profit_factor=5.0)

    stats = compute_summary_stats([low, high], best_metric="profit_factor")

    assert stats.best_experiment.experiment_id == "b"
    assert stats.best_experiment_metric == "profit_factor"


def test_compute_summary_stats_best_experiment_none_when_metric_all_null() -> None:
    records = [_record(sharpe_ratio=None)]

    stats = compute_summary_stats(records, best_metric="sharpe")

    assert stats.best_experiment is None
    assert stats.best_experiment_metric is None


def test_compute_summary_stats_raises_on_unknown_best_metric() -> None:
    with pytest.raises(ValueError):
        compute_summary_stats([_record()], best_metric="not_a_metric")


def test_compute_summary_stats_handles_empty_records() -> None:
    stats = compute_summary_stats([], best_metric=None)

    assert stats.total_experiments == 0
    assert stats.avg_profit_factor is None

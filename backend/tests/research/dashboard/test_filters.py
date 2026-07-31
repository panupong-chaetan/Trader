from __future__ import annotations

from datetime import datetime, timezone

from research.dashboard.filters import filter_records
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


def test_filter_records_returns_everything_with_no_filters() -> None:
    records = [_record(), _record(experiment_id="b")]

    assert filter_records(records) == records


def test_filter_records_matches_category_by_substring() -> None:
    records = [_record(category="trend_following"), _record(experiment_id="b", category="mean_reversion")]

    result = filter_records(records, category="trend")

    assert len(result) == 1
    assert result[0].category == "trend_following"


def test_filter_records_matches_market_ignoring_slash_and_case() -> None:
    records = [_record(market="BTC/USDT")]

    result = filter_records(records, market="btcusdt")

    assert result == records


def test_filter_records_matches_timeframe_exact() -> None:
    records = [_record(timeframe="15m"), _record(experiment_id="b", timeframe="1h")]

    result = filter_records(records, timeframe="15m")

    assert len(result) == 1
    assert result[0].timeframe == "15m"


def test_filter_records_combines_filters_with_and_semantics() -> None:
    records = [
        _record(category="trend_following", market="BTC/USDT"),
        _record(experiment_id="b", category="trend_following", market="ETH/USDT"),
    ]

    result = filter_records(records, category="trend", market="btc")

    assert len(result) == 1
    assert result[0].market == "BTC/USDT"


def test_filter_records_returns_empty_list_when_nothing_matches() -> None:
    records = [_record()]

    result = filter_records(records, category="mean_reversion")

    assert result == []

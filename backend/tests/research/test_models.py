from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from research.models import StrategyCatalogRecord


def _sample_kwargs() -> dict:
    return dict(
        experiment_id="donchian_breakout_20260801T120000_abcd1234",
        strategy_name="donchian_breakout",
        category="breakout",
        hypothesis="Closes beyond a 20-period channel continue in that direction.",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=42,
        total_trades=38,
        win_rate=0.45,
        profit_factor=1.3,
        expectancy=12.5,
        sharpe_ratio=0.9,
        max_drawdown=0.12,
        total_return=8.4,
        total_fees=120.0,
        rejected_signals=4,
        report_directory="reports/run_20260801T120000_abcd1234",
        created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_strategy_catalog_record_accepts_all_fields() -> None:
    record = StrategyCatalogRecord(**_sample_kwargs())

    assert record.strategy_name == "donchian_breakout"
    assert record.experiment_id == "donchian_breakout_20260801T120000_abcd1234"


def test_strategy_catalog_record_is_frozen() -> None:
    record = StrategyCatalogRecord(**_sample_kwargs())

    with pytest.raises(ValidationError):
        record.strategy_name = "changed"


def test_strategy_catalog_record_accepts_none_metrics() -> None:
    kwargs = _sample_kwargs()
    kwargs.update(win_rate=None, profit_factor=None, expectancy=None, sharpe_ratio=None, max_drawdown=None)

    record = StrategyCatalogRecord(**kwargs)

    assert record.win_rate is None
    assert record.profit_factor is None


def test_strategy_catalog_record_requires_all_fields() -> None:
    kwargs = _sample_kwargs()
    del kwargs["strategy_name"]

    with pytest.raises(ValidationError):
        StrategyCatalogRecord(**kwargs)

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.models import BacktestConfig
from report.builder import ReportSummary
from research.catalog import load_catalog, register_strategy_result
from research.models import StrategyCatalogRecord


def _sample_summary() -> ReportSummary:
    return ReportSummary(
        symbol="BTC/USDT",
        timeframe="15m",
        exchange="binance",
        dataset_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        dataset_end=datetime(2024, 6, 1, tzinfo=timezone.utc),
        dataset_status="complete",
        gap_warnings=[],
        config=BacktestConfig(
            initial_capital=10000.0,
            leverage=1.0,
            risk_per_trade_pct=1.0,
            fee_pct=0.04,
            slippage_pct=0.01,
        ),
        num_signals=42,
        num_trades=38,
        num_rejected_signals=4,
        initial_equity=10000.0,
        final_equity=10840.0,
        net_pnl=840.0,
        return_pct=8.4,
        win_rate=0.45,
        profit_factor=1.3,
        expectancy=12.5,
        sharpe_ratio=0.9,
        max_drawdown_pct=0.12,
        max_consecutive_losses=3,
        total_fees_paid=120.0,
        exit_reason_counts={"take_profit": 20, "stop_loss": 18},
    )


def _sample_record(catalog_dir: Path, **overrides) -> StrategyCatalogRecord:
    kwargs = dict(
        summary=_sample_summary(),
        strategy_name="donchian_breakout",
        category="breakout",
        hypothesis="Closes beyond a 20-period channel continue in that direction.",
        report_directory=Path("reports/run_a"),
        catalog_dir=catalog_dir,
    )
    kwargs.update(overrides)
    return register_strategy_result(**kwargs)


def test_register_strategy_result_writes_one_new_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"

    record = _sample_record(catalog_dir)

    files = list(catalog_dir.glob("*.json"))
    assert len(files) == 1
    assert files[0].stem == record.experiment_id


def test_register_strategy_result_maps_report_summary_fields(tmp_path: Path) -> None:
    summary = _sample_summary()

    record = _sample_record(tmp_path / "catalog", summary=summary)

    assert record.market == summary.symbol
    assert record.timeframe == summary.timeframe
    assert record.start_date == summary.dataset_start
    assert record.end_date == summary.dataset_end
    assert record.initial_capital == summary.config.initial_capital
    assert record.total_signals == summary.num_signals
    assert record.total_trades == summary.num_trades
    assert record.rejected_signals == summary.num_rejected_signals
    assert record.win_rate == summary.win_rate
    assert record.profit_factor == summary.profit_factor
    assert record.expectancy == summary.expectancy
    assert record.sharpe_ratio == summary.sharpe_ratio
    assert record.max_drawdown == summary.max_drawdown_pct
    assert record.total_return == summary.return_pct
    assert record.total_fees == summary.total_fees_paid
    assert record.report_directory == str(Path("reports/run_a"))


def test_register_strategy_result_never_touches_previous_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    first = _sample_record(catalog_dir, hypothesis="First run.")
    first_path = catalog_dir / f"{first.experiment_id}.json"
    first_content_before = first_path.read_text()

    _sample_record(catalog_dir, hypothesis="Second run.")

    assert first_path.read_text() == first_content_before
    assert len(list(catalog_dir.glob("*.json"))) == 2


def test_register_strategy_result_twice_produces_distinct_experiment_ids(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"

    first = _sample_record(catalog_dir, hypothesis="First run.")
    second = _sample_record(catalog_dir, hypothesis="Second run.")

    assert first.experiment_id != second.experiment_id


def test_load_catalog_round_trips_a_registered_record(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    registered = _sample_record(catalog_dir)

    loaded = load_catalog(catalog_dir)

    assert loaded == [registered]


def test_load_catalog_orders_by_created_at(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir(parents=True)

    older = StrategyCatalogRecord(
        experiment_id="strat_a_20260101T000000_11111111",
        strategy_name="strat_a",
        category="breakout",
        hypothesis="h",
        market="BTC/USDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=10000.0,
        total_signals=1,
        total_trades=1,
        win_rate=None,
        profit_factor=None,
        expectancy=None,
        sharpe_ratio=None,
        max_drawdown=None,
        total_return=1.0,
        total_fees=1.0,
        rejected_signals=0,
        report_directory="reports/run_a",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = older.model_copy(
        update={
            "experiment_id": "strat_b_20260201T000000_22222222",
            "strategy_name": "strat_b",
            "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        }
    )

    (catalog_dir / f"{newer.experiment_id}.json").write_text(newer.model_dump_json())
    (catalog_dir / f"{older.experiment_id}.json").write_text(older.model_dump_json())

    loaded = load_catalog(catalog_dir)

    assert [r.experiment_id for r in loaded] == [older.experiment_id, newer.experiment_id]


def test_load_catalog_raises_on_malformed_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "broken.json").write_text("{not valid json")

    with pytest.raises(ValueError):
        load_catalog(catalog_dir)


def test_load_catalog_returns_empty_list_for_missing_directory(tmp_path: Path) -> None:
    assert load_catalog(tmp_path / "does_not_exist") == []

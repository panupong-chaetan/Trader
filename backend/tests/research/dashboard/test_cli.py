from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.dashboard.cli import build_parser, main
from research.models import StrategyCatalogRecord


def _write_record(catalog_dir: Path, **overrides) -> StrategyCatalogRecord:
    base = dict(
        experiment_id=overrides.get("experiment_id", "strat_a_20260101T000000_11111111"),
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
    record = StrategyCatalogRecord(**base)
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / f"{record.experiment_id}.json").write_text(record.model_dump_json())
    return record


def test_build_parser_defaults() -> None:
    args = build_parser().parse_args([])

    assert args.category is None
    assert args.order == "desc"


def test_main_prints_table_and_stats(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir, experiment_id="a", strategy_name="strat_a", profit_factor=1.0)
    _write_record(catalog_dir, experiment_id="b", strategy_name="strat_b", profit_factor=3.0)

    exit_code = main(["--catalog-dir", str(catalog_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strat_a" in captured.out
    assert "strat_b" in captured.out
    assert "Total experiments: 2" in captured.out
    assert "Best experiment: N/A" in captured.out


def test_main_applies_filters(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir, experiment_id="a", strategy_name="strat_a", category="trend_following")
    _write_record(catalog_dir, experiment_id="b", strategy_name="strat_b", category="mean_reversion")

    exit_code = main(["--catalog-dir", str(catalog_dir), "--category", "trend"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strat_a" in captured.out
    assert "strat_b" not in captured.out


def test_main_sorts_and_reports_best_experiment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir, experiment_id="a", strategy_name="strat_a", profit_factor=1.0)
    _write_record(catalog_dir, experiment_id="b", strategy_name="strat_b", profit_factor=3.0)

    exit_code = main(["--catalog-dir", str(catalog_dir), "--sort", "profit_factor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Best experiment (profit_factor): strat_b" in captured.out


def test_main_exports_csv_and_markdown(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir)
    csv_path = tmp_path / "out.csv"
    md_path = tmp_path / "out.md"

    exit_code = main(
        [
            "--catalog-dir", str(catalog_dir),
            "--export-csv", str(csv_path),
            "--export-markdown", str(md_path),
        ]
    )

    assert exit_code == 0
    assert csv_path.exists()
    assert md_path.exists()


def test_main_returns_error_code_on_invalid_sort(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    _write_record(catalog_dir)

    exit_code = main(["--catalog-dir", str(catalog_dir), "--sort", "not_a_metric"])

    assert exit_code == 1

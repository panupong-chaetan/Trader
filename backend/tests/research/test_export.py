from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from research.export import export_catalog_csv, export_catalog_json
from research.models import StrategyCatalogRecord


def _record() -> StrategyCatalogRecord:
    return StrategyCatalogRecord(
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


def test_export_catalog_csv_writes_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"

    export_catalog_csv([_record()], path)

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["experiment_id"] == "strat_a_20260101T000000_11111111"
    assert rows[0]["strategy_name"] == "strat_a"
    assert set(rows[0].keys()) == set(StrategyCatalogRecord.model_fields.keys())


def test_export_catalog_json_writes_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"

    export_catalog_json([_record()], path)

    payload = json.loads(path.read_text())
    assert len(payload) == 1
    assert payload[0]["experiment_id"] == "strat_a_20260101T000000_11111111"
    assert set(payload[0].keys()) == set(StrategyCatalogRecord.model_fields.keys())


def test_export_catalog_json_overwrites_previous_export_file(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    export_catalog_json([_record()], path)

    export_catalog_json([], path)

    assert json.loads(path.read_text()) == []

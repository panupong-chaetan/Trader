from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from report.builder import ReportSummary

from research.models import StrategyCatalogRecord

logger = logging.getLogger(__name__)


def _build_experiment_id(strategy_name: str, created_at: datetime) -> str:
    return f"{strategy_name}_{created_at:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"


def register_strategy_result(
    summary: ReportSummary,
    strategy_name: str,
    category: str,
    hypothesis: str,
    report_directory: Path,
    catalog_dir: Path,
) -> StrategyCatalogRecord:
    created_at = datetime.now(timezone.utc)
    experiment_id = _build_experiment_id(strategy_name, created_at)

    record = StrategyCatalogRecord(
        experiment_id=experiment_id,
        strategy_name=strategy_name,
        category=category,
        hypothesis=hypothesis,
        market=summary.symbol,
        timeframe=summary.timeframe,
        start_date=summary.dataset_start,
        end_date=summary.dataset_end,
        initial_capital=summary.config.initial_capital,
        total_signals=summary.num_signals,
        total_trades=summary.num_trades,
        win_rate=summary.win_rate,
        profit_factor=summary.profit_factor,
        expectancy=summary.expectancy,
        sharpe_ratio=summary.sharpe_ratio,
        max_drawdown=summary.max_drawdown_pct,
        total_return=summary.return_pct,
        total_fees=summary.total_fees_paid,
        rejected_signals=summary.num_rejected_signals,
        report_directory=str(report_directory),
        created_at=created_at,
    )

    catalog_dir.mkdir(parents=True, exist_ok=True)
    record_path = catalog_dir / f"{experiment_id}.json"
    if record_path.exists():
        raise FileExistsError(f"catalog record already exists: {record_path}")

    record_path.write_text(record.model_dump_json(indent=2))
    logger.info("registered strategy result %s -> %s", strategy_name, record_path)
    return record


def load_catalog(catalog_dir: Path) -> list[StrategyCatalogRecord]:
    records: list[StrategyCatalogRecord] = []
    for path in sorted(catalog_dir.glob("*.json")):
        try:
            records.append(StrategyCatalogRecord.model_validate_json(path.read_text()))
        except Exception as exc:
            raise ValueError(f"failed to parse catalog record {path}: {exc}") from exc

    records.sort(key=lambda record: record.created_at)
    return records

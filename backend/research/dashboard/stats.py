from __future__ import annotations

from dataclasses import dataclass

from research.dashboard.sorting import SORT_FIELDS
from research.models import StrategyCatalogRecord


@dataclass(frozen=True)
class SummaryStats:
    total_experiments: int
    avg_profit_factor: float | None
    avg_sharpe: float | None
    avg_max_drawdown: float | None
    best_experiment_metric: str | None
    best_experiment: StrategyCatalogRecord | None


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute_summary_stats(
    records: list[StrategyCatalogRecord],
    best_metric: str | None,
) -> SummaryStats:
    avg_profit_factor = _average([r.profit_factor for r in records if r.profit_factor is not None])
    avg_sharpe = _average([r.sharpe_ratio for r in records if r.sharpe_ratio is not None])
    avg_max_drawdown = _average([r.max_drawdown for r in records if r.max_drawdown is not None])

    best_experiment: StrategyCatalogRecord | None = None
    if best_metric is not None:
        if best_metric not in SORT_FIELDS:
            raise ValueError(f"unknown sort key: {best_metric!r}")
        field = SORT_FIELDS[best_metric]
        candidates = [r for r in records if getattr(r, field) is not None]
        if candidates:
            best_experiment = max(candidates, key=lambda r: getattr(r, field))

    return SummaryStats(
        total_experiments=len(records),
        avg_profit_factor=avg_profit_factor,
        avg_sharpe=avg_sharpe,
        avg_max_drawdown=avg_max_drawdown,
        best_experiment_metric=best_metric if best_experiment is not None else None,
        best_experiment=best_experiment,
    )

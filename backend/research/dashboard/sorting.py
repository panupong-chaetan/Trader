from __future__ import annotations

from research.models import StrategyCatalogRecord

SORT_FIELDS: dict[str, str] = {
    "profit_factor": "profit_factor",
    "sharpe": "sharpe_ratio",
    "expectancy": "expectancy",
    "win_rate": "win_rate",
    "max_drawdown": "max_drawdown",
    "total_return": "total_return",
    "trades": "total_trades",
    "fees": "total_fees",
    "created_at": "created_at",
    "strategy": "strategy_name",
    "category": "category",
}


def sort_records(
    records: list[StrategyCatalogRecord],
    sort_key: str | None,
    descending: bool = True,
) -> list[StrategyCatalogRecord]:
    if sort_key is None:
        field = "created_at"
    elif sort_key in SORT_FIELDS:
        field = SORT_FIELDS[sort_key]
    else:
        raise ValueError(f"unknown sort key: {sort_key!r}")

    with_value = [r for r in records if getattr(r, field) is not None]
    without_value = [r for r in records if getattr(r, field) is None]

    with_value.sort(key=lambda r: getattr(r, field), reverse=descending)
    return with_value + without_value

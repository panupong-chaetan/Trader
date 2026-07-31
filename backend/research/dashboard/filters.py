from __future__ import annotations

import re

from research.models import StrategyCatalogRecord

_NORMALIZE_RE = re.compile(r"[^a-z0-9]")


def _normalize(value: str) -> str:
    return _NORMALIZE_RE.sub("", value.lower())


def filter_records(
    records: list[StrategyCatalogRecord],
    category: str | None = None,
    market: str | None = None,
    timeframe: str | None = None,
) -> list[StrategyCatalogRecord]:
    filtered = records
    if category is not None:
        needle = _normalize(category)
        filtered = [r for r in filtered if needle in _normalize(r.category)]
    if market is not None:
        needle = _normalize(market)
        filtered = [r for r in filtered if needle in _normalize(r.market)]
    if timeframe is not None:
        needle = _normalize(timeframe)
        filtered = [r for r in filtered if needle in _normalize(r.timeframe)]
    return filtered

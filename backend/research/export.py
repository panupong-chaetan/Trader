from __future__ import annotations

import csv
import json
from pathlib import Path

from research.models import StrategyCatalogRecord

_FIELDS = list(StrategyCatalogRecord.model_fields.keys())


def export_catalog_csv(records: list[StrategyCatalogRecord], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.model_dump(mode="json"))


def export_catalog_json(records: list[StrategyCatalogRecord], path: Path) -> None:
    payload = [record.model_dump(mode="json") for record in records]
    path.write_text(json.dumps(payload, indent=2))

from __future__ import annotations

from pathlib import Path

import polars as pl

from data.storage import dataset_paths, read_metadata_if_exists, read_parquet_if_exists
from engine.models import DatasetQuality, GapRange


def load_dataset(
    base_dir: Path,
    exchange: str,
    symbol_slug: str,
    timeframe: str,
) -> tuple[pl.DataFrame, DatasetQuality]:
    paths = dataset_paths(base_dir, exchange, symbol_slug, timeframe)

    df = read_parquet_if_exists(paths.parquet_path)
    if df is None:
        raise FileNotFoundError(f"No dataset found at {paths.parquet_path}")

    metadata = read_metadata_if_exists(paths.metadata_path)
    if metadata is None:
        raise FileNotFoundError(f"No metadata found at {paths.metadata_path}")

    gaps = [
        GapRange(start=g.start, end=g.end, severity=g.severity)
        for g in metadata.gaps
    ]
    return df, DatasetQuality(status=metadata.status, gaps=gaps)

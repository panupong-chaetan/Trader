from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from pydantic import BaseModel

from data.config import DownloadConfig
from data.validator import Gap, find_gaps

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class GapRecord(BaseModel):
    start: datetime
    end: datetime
    missing_candles: int
    severity: str


class DatasetMetadata(BaseModel):
    schema_version: int = SCHEMA_VERSION
    symbol: str
    timeframe: str
    exchange: str
    status: str
    start: datetime
    end: datetime
    row_count: int
    gaps: list[GapRecord]
    last_updated: datetime


@dataclass(frozen=True)
class DatasetPaths:
    parquet_path: Path
    metadata_path: Path


def dataset_paths(base_dir: Path, exchange: str, symbol_slug: str, timeframe: str) -> DatasetPaths:
    directory = base_dir / "ohlcv" / exchange / symbol_slug
    return DatasetPaths(
        parquet_path=directory / f"{timeframe}.parquet",
        metadata_path=directory / f"{timeframe}.metadata.json",
    )


def read_parquet_if_exists(path: Path) -> pl.DataFrame | None:
    if not path.exists():
        return None
    return pl.read_parquet(path)


def read_metadata_if_exists(path: Path) -> DatasetMetadata | None:
    if not path.exists():
        return None
    return DatasetMetadata.model_validate_json(path.read_text())


def build_metadata(
    df: pl.DataFrame,
    config: DownloadConfig,
    gaps: list[Gap],
    status: str,
) -> DatasetMetadata:
    timestamps = df["timestamp"]
    return DatasetMetadata(
        symbol=config.symbol,
        timeframe=config.timeframe,
        exchange=config.exchange,
        status=status,
        start=timestamps.min(),
        end=timestamps.max(),
        row_count=df.height,
        gaps=[
            GapRecord(start=g.start, end=g.end, missing_candles=g.missing_candles, severity=g.severity)
            for g in gaps
        ],
        last_updated=datetime.now(timezone.utc),
    )


def reconcile_metadata(
    df: pl.DataFrame,
    metadata: DatasetMetadata | None,
    config: DownloadConfig,
) -> DatasetMetadata | None:
    if metadata is None:
        return None

    actual_end = df["timestamp"].max()
    if actual_end == metadata.end:
        return metadata

    logger.warning(
        "Metadata end %s disagrees with Parquet last timestamp %s; regenerating metadata",
        metadata.end,
        actual_end,
    )
    gaps = find_gaps(df, config.timeframe, config.small_gap_max, config.medium_gap_max)
    status = "incomplete" if gaps else "complete"
    return build_metadata(df, config, gaps, status)


def atomic_write(df: pl.DataFrame, metadata: DatasetMetadata, paths: DatasetPaths) -> None:
    paths.parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_tmp = paths.parquet_path.with_name(paths.parquet_path.name + ".tmp")
    metadata_tmp = paths.metadata_path.with_name(paths.metadata_path.name + ".tmp")

    try:
        df.write_parquet(parquet_tmp)
        metadata_tmp.write_text(metadata.model_dump_json(indent=2))
        parquet_tmp.replace(paths.parquet_path)
        metadata_tmp.replace(paths.metadata_path)
    except Exception:
        parquet_tmp.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)
        raise

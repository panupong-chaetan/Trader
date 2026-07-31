from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator


class DownloadConfig(BaseModel):
    exchange: str
    symbol: str
    timeframe: str
    start: datetime
    end: datetime | None = None
    small_gap_max: int = 5
    medium_gap_max: int = 20
    retry_count: int = 1

    @field_validator("small_gap_max", "medium_gap_max", "retry_count")
    @classmethod
    def _must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> "DownloadConfig":
        if self.medium_gap_max <= self.small_gap_max:
            raise ValueError("medium_gap_max must be greater than small_gap_max")
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be after start")
        return self

    @property
    def symbol_slug(self) -> str:
        return self.symbol.replace("/", "")

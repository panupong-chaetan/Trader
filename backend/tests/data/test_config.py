from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data.config import DownloadConfig


def _base_kwargs() -> dict:
    return {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "start": datetime(2020, 1, 1, tzinfo=timezone.utc),
    }


def test_download_config_accepts_valid_input() -> None:
    config = DownloadConfig(**_base_kwargs())

    assert config.exchange == "binance"
    assert config.small_gap_max == 5
    assert config.medium_gap_max == 20
    assert config.retry_count == 1


def test_download_config_symbol_slug_strips_separator() -> None:
    config = DownloadConfig(**_base_kwargs())

    assert config.symbol_slug == "BTCUSDT"


def test_download_config_rejects_end_before_start() -> None:
    kwargs = _base_kwargs()
    kwargs["end"] = datetime(2019, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        DownloadConfig(**kwargs)


def test_download_config_rejects_medium_not_greater_than_small() -> None:
    kwargs = _base_kwargs()
    kwargs["small_gap_max"] = 10
    kwargs["medium_gap_max"] = 10

    with pytest.raises(ValidationError):
        DownloadConfig(**kwargs)


def test_download_config_rejects_non_positive_retry_count() -> None:
    kwargs = _base_kwargs()
    kwargs["retry_count"] = 0

    with pytest.raises(ValidationError):
        DownloadConfig(**kwargs)

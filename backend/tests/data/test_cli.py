from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import data.cli as cli_module
from data.cli import build_parser, main

INTERVAL = timedelta(minutes=15)
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


class ListFetcher:
    def __init__(self, candles):
        self._candles = candles

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return [c for c in self._candles if c[0] >= since][:limit]


def _candle(ts, price=100.0):
    return [int(ts.timestamp() * 1000), price, price, price, price, 1.0]


def test_build_parser_parses_download_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["download", "--symbol", "BTC/USDT", "--timeframe", "15m", "--start", "2024-01-01T00:00:00"]
    )

    assert args.symbol == "BTC/USDT"
    assert args.timeframe == "15m"
    assert args.retry_count == 1


def test_main_returns_zero_on_successful_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", tmp_path)
    candles = [_candle(START + i * INTERVAL, 100.0 + i) for i in range(5)]
    monkeypatch.setattr(cli_module, "create_ccxt_fetcher", lambda exchange: ListFetcher(candles))

    exit_code = main(
        [
            "download",
            "--symbol", "BTC/USDT",
            "--timeframe", "15m",
            "--start", "2024-01-01T00:00:00",
            "--end", "2024-01-01T01:00:00",
        ]
    )

    assert exit_code == 0


def test_main_returns_one_on_data_integrity_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "DEFAULT_DATA_DIR", tmp_path)
    candles = [_candle(START + i * INTERVAL, 100.0 + i) for i in range(30) if i not in set(range(2, 25))]
    monkeypatch.setattr(cli_module, "create_ccxt_fetcher", lambda exchange: ListFetcher(candles))

    exit_code = main(
        [
            "download",
            "--symbol", "BTC/USDT",
            "--timeframe", "15m",
            "--start", "2024-01-01T00:00:00",
            "--end", "2024-01-01T07:15:00",
        ]
    )

    assert exit_code == 1

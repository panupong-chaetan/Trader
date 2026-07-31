import polars as pl
import pytest

from strategy.indicators import atr, ema


def test_ema_matches_documented_formula_end_to_end() -> None:
    df = pl.DataFrame({"close": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]})

    result = ema(df, "close", 3).to_list()

    assert result[0] is None
    assert result[1] is None

    alpha = 2 / (3 + 1)
    closes = df["close"].to_list()
    expected = [sum(closes[:3]) / 3]
    for i in range(3, 6):
        expected.append(closes[i] * alpha + expected[-1] * (1 - alpha))

    assert result[2:] == pytest.approx(expected)


def test_ema_returns_all_null_when_shorter_than_period() -> None:
    df = pl.DataFrame({"close": [10.0, 11.0]})

    result = ema(df, "close", 5).to_list()

    assert result == [None, None]


def test_atr_matches_documented_formula_end_to_end() -> None:
    df = pl.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 13.0, 9.0, 10.0],
            "low": [8.0, 9.0, 10.0, 11.0, 7.0, 8.0],
            "close": [9.0, 10.0, 11.0, 12.0, 8.0, 9.0],
        }
    )

    result = atr(df, 3).to_list()

    assert result[:3] == [None, None, None]

    true_ranges = [None, 2.0, 2.0, 2.0, 5.0, 2.0]
    seed = sum(true_ranges[1:4]) / 3
    expected = [seed]
    for i in range(4, 6):
        expected.append((expected[-1] * (3 - 1) + true_ranges[i]) / 3)

    assert result[3:] == pytest.approx(expected)


def test_atr_index_zero_and_before_seed_are_null() -> None:
    df = pl.DataFrame(
        {
            "high": [10.0, 11.0, 12.0],
            "low": [8.0, 9.0, 10.0],
            "close": [9.0, 10.0, 11.0],
        }
    )

    result = atr(df, 5).to_list()

    assert result == [None, None, None]

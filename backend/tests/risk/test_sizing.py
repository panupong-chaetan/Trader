import pytest

from engine.models import BacktestConfig
from risk.sizing import size_position


def _config(**overrides) -> BacktestConfig:
    kwargs = dict(
        initial_capital=10000.0,
        leverage=1.0,
        risk_per_trade_pct=0.01,
        fee_pct=0.001,
        slippage_pct=0.0005,
    )
    kwargs.update(overrides)
    return BacktestConfig(**kwargs)


def test_size_position_long_valid_matches_documented_formula() -> None:
    config = _config()
    entry, stop, equity = 100.0, 95.0, 10000.0

    stop_exit_price = stop * (1 - config.slippage_pct)
    price_risk = entry - stop_exit_price
    fee_cost = config.fee_pct * (entry + stop_exit_price)
    effective_risk = price_risk + fee_cost
    expected_quantity = (equity * config.risk_per_trade_pct) / effective_risk

    result = size_position("long", entry, stop, equity, config)

    assert result.accepted
    assert result.quantity == pytest.approx(expected_quantity)


def test_size_position_short_valid_matches_documented_formula() -> None:
    config = _config()
    entry, stop, equity = 100.0, 105.0, 10000.0

    stop_exit_price = stop * (1 + config.slippage_pct)
    price_risk = stop_exit_price - entry
    fee_cost = config.fee_pct * (entry + stop_exit_price)
    effective_risk = price_risk + fee_cost
    expected_quantity = (equity * config.risk_per_trade_pct) / effective_risk

    result = size_position("short", entry, stop, equity, config)

    assert result.accepted
    assert result.quantity == pytest.approx(expected_quantity)


def test_size_position_capital_cap_binds_reduces_quantity() -> None:
    config = _config(risk_per_trade_pct=0.5, leverage=1.0)
    entry, stop, equity = 100.0, 99.0, 10000.0

    result = size_position("long", entry, stop, equity, config)

    capital_capped_quantity = (equity * config.leverage) / entry
    assert result.accepted
    assert result.quantity == pytest.approx(capital_capped_quantity)


def test_size_position_rejects_invalid_stop_placement_for_long() -> None:
    config = _config()

    result = size_position("long", 100.0, 105.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "invalid_stop_placement"


def test_size_position_rejects_invalid_stop_placement_for_short() -> None:
    config = _config()

    result = size_position("short", 100.0, 95.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "invalid_stop_placement"


def test_size_position_rejects_zero_stop_distance_for_long() -> None:
    config = _config()

    result = size_position("long", 100.0, 100.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "zero_stop_distance"


def test_size_position_rejects_zero_stop_distance_for_short() -> None:
    config = _config()

    result = size_position("short", 100.0, 100.0, 10000.0, config)

    assert not result.accepted
    assert result.reason == "zero_stop_distance"


def test_size_position_rejects_insufficient_capital_when_equity_zero() -> None:
    config = _config()

    result = size_position("long", 100.0, 95.0, 0.0, config)

    assert not result.accepted
    assert result.reason == "insufficient_capital"


def test_size_position_rejects_insufficient_capital_when_equity_negative() -> None:
    config = _config()

    result = size_position("long", 100.0, 95.0, -500.0, config)

    assert not result.accepted
    assert result.reason == "insufficient_capital"

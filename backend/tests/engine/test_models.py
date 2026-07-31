import pytest
from pydantic import ValidationError

from engine.models import BacktestConfig


def _base_kwargs() -> dict:
    return {
        "initial_capital": 10000.0,
        "risk_per_trade_pct": 0.01,
        "fee_pct": 0.001,
        "slippage_pct": 0.0005,
    }


def test_backtest_config_accepts_valid_input() -> None:
    config = BacktestConfig(**_base_kwargs())

    assert config.initial_capital == 10000.0
    assert config.leverage == 1.0
    assert config.allow_incomplete_dataset is False


def test_backtest_config_rejects_non_positive_initial_capital() -> None:
    kwargs = _base_kwargs()
    kwargs["initial_capital"] = 0.0

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_non_positive_risk_per_trade_pct() -> None:
    kwargs = _base_kwargs()
    kwargs["risk_per_trade_pct"] = 0.0

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_leverage_below_one() -> None:
    kwargs = _base_kwargs()
    kwargs["leverage"] = 0.5

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_negative_fee_pct() -> None:
    kwargs = _base_kwargs()
    kwargs["fee_pct"] = -0.001

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)


def test_backtest_config_rejects_negative_slippage_pct() -> None:
    kwargs = _base_kwargs()
    kwargs["slippage_pct"] = -0.0001

    with pytest.raises(ValidationError):
        BacktestConfig(**kwargs)

from pathlib import Path

import pytest

from strategies.contracts import assert_no_forbidden_imports

STRATEGIES_DIR = Path(__file__).resolve().parents[2] / "strategies"


def _write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.write_text(source)
    return path


def test_assert_no_forbidden_imports_passes_clean_module(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "clean.py",
        "import polars as pl\nfrom engine.models import Signal\n\n"
        "def generate_signals(ohlcv: pl.DataFrame) -> list[Signal]:\n    return []\n",
    )

    assert_no_forbidden_imports(path)


def test_assert_no_forbidden_imports_fails_on_risk_import(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad_risk.py", "import risk.sizing\n")

    with pytest.raises(AssertionError):
        assert_no_forbidden_imports(path)


def test_assert_no_forbidden_imports_fails_on_engine_backtester_import(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad_engine.py", "from engine.backtester import run\n")

    with pytest.raises(AssertionError):
        assert_no_forbidden_imports(path)


def test_assert_no_forbidden_imports_fails_on_forbidden_import_inside_function(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad_nested.py",
        "def generate_signals(ohlcv):\n    import analytics.metrics\n    return []\n",
    )

    with pytest.raises(AssertionError):
        assert_no_forbidden_imports(path)


def test_assert_no_forbidden_imports_allows_engine_models_import(tmp_path: Path) -> None:
    path = _write(tmp_path, "ok_engine_models.py", "from engine.models import Signal\n")

    assert_no_forbidden_imports(path)


def test_no_strategy_module_imports_forbidden_packages() -> None:
    for path in STRATEGIES_DIR.glob("*.py"):
        if path.name in ("__init__.py", "contracts.py"):
            continue
        assert_no_forbidden_imports(path)

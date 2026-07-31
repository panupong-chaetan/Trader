from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable

import polars as pl

from engine.models import Signal

GenerateSignals = Callable[[pl.DataFrame], list[Signal]]

FORBIDDEN_IMPORT_ROOTS = ("risk", "analytics", "report", "runner", "engine.backtester")


def _is_forbidden(dotted_path: str) -> bool:
    return any(
        dotted_path == root or dotted_path.startswith(root + ".")
        for root in FORBIDDEN_IMPORT_ROOTS
    )


def assert_no_forbidden_imports(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(), filename=str(module_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not _is_forbidden(alias.name), (
                    f"{module_path.name} imports forbidden module '{alias.name}'"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                assert not _is_forbidden(node.module), (
                    f"{module_path.name} imports forbidden module '{node.module}'"
                )

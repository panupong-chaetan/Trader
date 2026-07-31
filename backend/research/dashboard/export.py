from __future__ import annotations

from pathlib import Path

import polars as pl


def export_table_csv(df: pl.DataFrame, path: Path) -> None:
    df.write_csv(path)


def export_table_markdown(df: pl.DataFrame, path: Path) -> None:
    header = "| " + " | ".join(df.columns) + " |"
    separator = "| " + " | ".join("---" for _ in df.columns) + " |"
    lines = [header, separator]
    for row in df.iter_rows():
        cells = ["" if value is None else str(value) for value in row]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n")

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from research.dashboard.export import export_table_csv, export_table_markdown


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Strategy": ["strat_a"],
            "Profit Factor": [1.4],
            "Sharpe": [None],
        }
    )


def test_export_table_csv_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"

    export_table_csv(_sample_df(), path)

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["Strategy"] == "strat_a"
    assert rows[0]["Profit Factor"] == "1.4"


def test_export_table_markdown_has_header_separator_and_row(tmp_path: Path) -> None:
    path = tmp_path / "table.md"

    export_table_markdown(_sample_df(), path)

    lines = path.read_text().splitlines()
    assert lines[0] == "| Strategy | Profit Factor | Sharpe |"
    assert lines[1] == "| --- | --- | --- |"
    assert lines[2] == "| strat_a | 1.4 |  |"


def test_export_table_markdown_handles_empty_dataframe(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    df = pl.DataFrame(
        {"Strategy": [], "Profit Factor": []},
        schema={"Strategy": pl.Utf8, "Profit Factor": pl.Float64},
    )

    export_table_markdown(df, path)

    lines = path.read_text().splitlines()
    assert lines[0] == "| Strategy | Profit Factor |"
    assert lines[1] == "| --- | --- |"
    assert len(lines) == 2

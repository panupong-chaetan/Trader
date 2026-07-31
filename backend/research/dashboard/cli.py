from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research.catalog import load_catalog
from research.dashboard.export import export_table_csv, export_table_markdown
from research.dashboard.filters import filter_records
from research.dashboard.sorting import sort_records
from research.dashboard.stats import compute_summary_stats
from research.dashboard.table import build_dashboard_table

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[3] / "research" / "catalog"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.research.dashboard.cli")
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_CATALOG_DIR)
    parser.add_argument("--category", default=None)
    parser.add_argument("--market", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--sort", default=None)
    parser.add_argument("--order", choices=["asc", "desc"], default="desc")
    parser.add_argument("--export-csv", type=Path, default=None)
    parser.add_argument("--export-markdown", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    parser = build_parser()
    args = parser.parse_args(argv)

    records = load_catalog(args.catalog_dir)
    filtered = filter_records(records, category=args.category, market=args.market, timeframe=args.timeframe)

    try:
        ordered = sort_records(filtered, sort_key=args.sort, descending=(args.order != "asc"))
        stats = compute_summary_stats(filtered, best_metric=args.sort)
    except ValueError as error:
        logger.error("Invalid --sort value: %s", error)
        return 1

    table = build_dashboard_table(ordered)
    print(table)

    print("\nSummary statistics")
    print(f"  Total experiments: {stats.total_experiments}")
    print(f"  Avg profit factor: {stats.avg_profit_factor}")
    print(f"  Avg Sharpe: {stats.avg_sharpe}")
    print(f"  Avg max drawdown: {stats.avg_max_drawdown}")
    if stats.best_experiment is not None:
        print(
            f"  Best experiment ({stats.best_experiment_metric}): "
            f"{stats.best_experiment.strategy_name} ({stats.best_experiment.experiment_id})"
        )
    else:
        print("  Best experiment: N/A (no --sort given, or no experiment has that metric)")

    if args.export_csv is not None:
        export_table_csv(table, args.export_csv)
        logger.info("Exported CSV to %s", args.export_csv)
    if args.export_markdown is not None:
        export_table_markdown(table, args.export_markdown)
        logger.info("Exported Markdown to %s", args.export_markdown)

    return 0


if __name__ == "__main__":
    sys.exit(main())

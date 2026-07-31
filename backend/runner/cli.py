from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from data.exceptions import DataIntegrityError
from engine.backtester import run
from engine.loader import load_dataset
from engine.models import BacktestConfig
from report.builder import build_summary
from report.export import write_equity_curve_parquet, write_summary_json, write_trades_csv
from strategy.ema_trend_pullback import generate_signals

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "reports"


def _create_run_directory(base_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    run_dir = base_dir / f"run_{timestamp}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.runner.cli")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--allow-incomplete-dataset", action="store_true")
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    parser.add_argument("--fee-pct", type=float, default=0.001)
    parser.add_argument("--slippage-pct", type=float, default=0.0005)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    parser = build_parser()
    args = parser.parse_args(argv)

    symbol_slug = args.symbol.replace("/", "")

    try:
        ohlcv, dataset_quality = load_dataset(DEFAULT_DATA_DIR, args.exchange, symbol_slug, args.timeframe)
    except FileNotFoundError as error:
        logger.error("Dataset load failed: %s", error)
        return 1

    config = BacktestConfig(
        initial_capital=args.initial_capital,
        leverage=args.leverage,
        risk_per_trade_pct=args.risk_per_trade_pct,
        fee_pct=args.fee_pct,
        slippage_pct=args.slippage_pct,
        allow_incomplete_dataset=args.allow_incomplete_dataset,
    )

    signals = generate_signals(ohlcv)

    try:
        result = run(ohlcv, signals, dataset_quality, config)
    except DataIntegrityError as error:
        logger.error("Backtest aborted: %s", error)
        return 1

    summary = build_summary(result, len(signals), args.symbol, args.timeframe, args.exchange)

    run_dir = _create_run_directory(args.output_dir)
    write_summary_json(summary, run_dir / "summary.json")
    write_trades_csv(result.trades, run_dir / "trades.csv")
    write_equity_curve_parquet(result.equity_curve, run_dir / "equity_curve.parquet")

    logger.info("Report written to %s", run_dir)
    logger.info(
        "Signals=%d Trades=%d Rejected=%d NetPnL=%.2f Return=%.2f%% WinRate=%s",
        summary.num_signals, summary.num_trades, summary.num_rejected_signals,
        summary.net_pnl, summary.return_pct, summary.win_rate,
    )
    logger.info("This is a hypothesis test only -- not a profitability claim.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

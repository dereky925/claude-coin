#!/usr/bin/env python3
"""
Backtest sweep: run backtests over symbols and strategy params (SMA, RSI, MACD).
Optionally validate top N combinations out-of-sample. Supports large symbol lists and long timeframes.

Usage:
  python3 backtest_sweep.py
  python3 backtest_sweep.py --strategy sma --symbols SPY,AAPL --start 2020-01-01 --csv sweep.csv
  python3 backtest_sweep.py --strategy all --large --start 2010-01-01 --oos-start 2024-01-01 --top 20 --csv sweep.csv
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from backtest import run_backtest, run_backtest_generic

# Large universe for exploring the space (indices, mega caps, sector ETFs, growth names)
LARGE_SYMBOLS = [
    "SPY", "QQQ", "IWM", "DIA",  # indices
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "V", "JNJ", "PG", "UNH", "HD", "DIS", "XOM", "CVX",  # mega
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU",  # sector ETFs
    "NFLX", "ADBE", "CRM", "ORCL", "AVGO", "AMD", "INTC", "QCOM", "TXN", "MU",  # tech
]

DEFAULT_START_LONG = "2010-01-01"  # long backtest default


def parse_symbols(s: str) -> list[str]:
    return [x.strip().upper() for x in s.split(",") if x.strip()]


def build_sma_param_grid(fast_periods: list[int], slow_periods: list[int]) -> list[dict]:
    grid = []
    for fast in fast_periods:
        for slow in slow_periods:
            if fast < slow:
                grid.append({"fast_period": fast, "slow_period": slow})
    return grid


def build_rsi_param_grid(
    periods: list[int] = (7, 14, 21),
    oversold: list[float] = (25.0, 30.0),
    overbought: list[float] = (70.0, 75.0),
) -> list[dict]:
    grid = []
    for p in periods:
        for o in oversold:
            for b in overbought:
                if o < b:
                    grid.append({"period": p, "oversold": o, "overbought": b})
    return grid


def build_macd_param_grid() -> list[dict]:
    # (fast, slow, signal) common variants
    return [
        {"fast_ema": 12, "slow_ema": 26, "signal_ema": 9},
        {"fast_ema": 8, "slow_ema": 17, "signal_ema": 9},
        {"fast_ema": 16, "slow_ema": 32, "signal_ema": 9},
        {"fast_ema": 12, "slow_ema": 26, "signal_ema": 6},
    ]


def run_sweep(
    symbols: list[str],
    start: str,
    end: str,
    strategy: str = "sma",
    param_grid: list[dict] | None = None,
    fast_periods: list[int] | None = None,
    slow_periods: list[int] | None = None,
    initial_capital: float = 100_000.0,
    max_drawdown_cap: float | None = None,
) -> pd.DataFrame:
    """
    Run backtest for each (symbol, params). strategy in (sma, rsi, macd).
    For sma, param_grid can be built from fast_periods/slow_periods if not provided.
    """
    if strategy == "sma" and param_grid is None:
        param_grid = build_sma_param_grid(fast_periods or [10], slow_periods or [30])
    elif strategy == "rsi" and param_grid is None:
        param_grid = build_rsi_param_grid()
    elif strategy == "macd" and param_grid is None:
        param_grid = build_macd_param_grid()
    if not param_grid:
        return pd.DataFrame()

    rows = []
    for symbol in symbols:
        for params in param_grid:
            try:
                _, metrics, _ = run_backtest_generic(
                    symbol=symbol,
                    start=start,
                    end=end,
                    initial_capital=initial_capital,
                    strategy=strategy,
                    **params,
                )
                spy_ret = metrics.get("spy_return_pct")
                excess = (metrics["total_return_pct"] - spy_ret) if spy_ret is not None else None
                row = {
                    "symbol": symbol,
                    "strategy": strategy,
                    "total_return_pct": metrics["total_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "n_trades": metrics["n_trades"],
                    "buy_hold_return_pct": metrics["buy_hold_return_pct"],
                    "spy_return_pct": spy_ret,
                    "excess_vs_spy": excess,
                }
                for k, v in params.items():
                    row[k] = v
                if max_drawdown_cap is not None and row["max_drawdown_pct"] < max_drawdown_cap:
                    continue
                rows.append(row)
            except Exception as e:
                print(f"  Skip {symbol} {strategy} {params}: {e}", file=sys.stderr)
                continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["excess_vs_spy", "total_return_pct"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)
    return df


def run_oos_validation(
    sweep_df: pd.DataFrame,
    top_n: int,
    oos_start: str,
    end: str,
    initial_capital: float = 100_000.0,
    min_oos_return_pct: float | None = None,
    min_oos_excess_vs_spy: float | None = None,
) -> pd.DataFrame:
    """Run backtest on OOS period for top N rows. Supports any strategy (sma/rsi/macd)."""
    top = sweep_df.head(top_n)
    if top.empty:
        return pd.DataFrame()
    strategy_param_keys = {
        "sma": ["fast_period", "slow_period"],
        "rsi": ["period", "oversold", "overbought"],
        "macd": ["fast_ema", "slow_ema", "signal_ema"],
    }
    rows = []
    for _, r in top.iterrows():
        symbol = r["symbol"]
        strategy = r.get("strategy", "sma")
        keys = strategy_param_keys.get(strategy, ["fast_period", "slow_period"])
        params = {k: r[k] for k in keys if k in r and pd.notna(r.get(k))}
        if strategy == "sma":
            params = {k: int(v) for k, v in params.items()}
        elif strategy == "rsi":
            params = {"period": int(params.get("period", 14)), "oversold": float(params.get("oversold", 30)), "overbought": float(params.get("overbought", 70))}
        elif strategy == "macd":
            params = {k: int(v) for k, v in params.items()}
        try:
            _, metrics, _ = run_backtest_generic(
                symbol=symbol,
                start=oos_start,
                end=end,
                initial_capital=initial_capital,
                strategy=strategy,
                **params,
            )
            spy_ret = metrics.get("spy_return_pct")
            excess = (metrics["total_return_pct"] - spy_ret) if spy_ret is not None else None
            pass_return = (metrics["total_return_pct"] >= min_oos_return_pct) if min_oos_return_pct is not None else True
            pass_excess = (excess is not None and excess >= min_oos_excess_vs_spy) if min_oos_excess_vs_spy is not None else True
            passed = pass_return and pass_excess
            out = {"symbol": symbol, "strategy": strategy, "oos_return_pct": metrics["total_return_pct"], "oos_max_drawdown_pct": metrics["max_drawdown_pct"], "oos_n_trades": metrics["n_trades"], "oos_spy_return_pct": spy_ret, "oos_excess_vs_spy": excess, "passed": passed}
            for k, v in params.items():
                out[k] = v
            rows.append(out)
        except Exception as e:
            print(f"  OOS skip {symbol} {strategy}: {e}", file=sys.stderr)
            out = {"symbol": symbol, "strategy": strategy, "oos_return_pct": None, "oos_max_drawdown_pct": None, "oos_n_trades": None, "oos_spy_return_pct": None, "oos_excess_vs_spy": None, "passed": False}
            for k in keys:
                out[k] = r.get(k)
            rows.append(out)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Sweep backtest over symbols and strategies (sma/rsi/macd); optional OOS validation."
    )
    parser.add_argument(
        "--strategy",
        choices=("sma", "rsi", "macd", "all"),
        default="sma",
        help="Strategy to sweep (default: sma). 'all' runs sma, rsi, macd and concatenates.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols (default: BOT_SYMBOLS or small default; overridden by --large)",
    )
    parser.add_argument(
        "--large",
        action="store_true",
        help="Use large symbol universe (40+ symbols) and default start 2010-01-01",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="In-sample start date YYYY-MM-DD (default: 2010-01-01 if --large, else 2020-01-01)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--fast",
        default="5,10,15,20",
        help="Comma-separated fast SMA periods (sma only)",
    )
    parser.add_argument(
        "--slow",
        default="20,30,40,50",
        help="Comma-separated slow SMA periods (sma only)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100_000.0,
        help="Initial capital",
    )
    parser.add_argument(
        "--max-dd-cap",
        type=float,
        default=None,
        metavar="PCT",
        help="Skip combos with max drawdown worse than this (e.g. -25)",
    )
    parser.add_argument(
        "--csv",
        metavar="FILE",
        default=None,
        help="Save sweep results to CSV",
    )
    parser.add_argument(
        "--oos-start",
        default=None,
        metavar="YYYY-MM-DD",
        help="If set, run OOS validation: backtest top N from sweep on [oos-start, end]",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top combos to validate OOS (default: 10)",
    )
    parser.add_argument(
        "--min-oos-return",
        type=float,
        default=None,
        metavar="PCT",
        help="OOS pass if strategy return >= this (e.g. 0)",
    )
    parser.add_argument(
        "--min-oos-excess",
        type=float,
        default=None,
        metavar="PCT",
        help="OOS pass if excess vs SPY >= this (e.g. -5)",
    )
    parser.add_argument(
        "--oos-csv",
        metavar="FILE",
        default=None,
        help="Save OOS validation results to CSV",
    )
    args = parser.parse_args()

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    if args.large:
        symbols = LARGE_SYMBOLS
        start = args.start or DEFAULT_START_LONG
    else:
        symbols = parse_symbols(args.symbols or os.getenv("BOT_SYMBOLS", "SPY,AAPL,QQQ,GOOGL,MSFT"))
        start = args.start or "2020-01-01"

    if args.oos_start:
        in_sample_end = args.oos_start
    else:
        in_sample_end = end

    fast_periods = [int(x.strip()) for x in args.fast.split(",") if x.strip()]
    slow_periods = [int(x.strip()) for x in args.slow.split(",") if x.strip()]

    strategies_to_run = ["sma", "rsi", "macd"] if args.strategy == "all" else [args.strategy]
    sweep_dfs = []

    for strat in strategies_to_run:
        print(f"In-sample: {start} → {in_sample_end}  strategy={strat}")
        print(f"Symbols: {len(symbols)} ({symbols[0]}, ...)" if len(symbols) > 1 else f"Symbols: {symbols}")
        if strat == "sma":
            print(f"Fast periods: {fast_periods}, Slow periods: {slow_periods}")
        print()
        df = run_sweep(
            symbols=symbols,
            start=start,
            end=in_sample_end,
            strategy=strat,
            fast_periods=fast_periods if strat == "sma" else None,
            slow_periods=slow_periods if strat == "sma" else None,
            initial_capital=args.capital,
            max_drawdown_cap=args.max_dd_cap,
        )
        if not df.empty:
            sweep_dfs.append(df)

    sweep_df = pd.concat(sweep_dfs, ignore_index=True) if sweep_dfs else pd.DataFrame()
    if not sweep_df.empty:
        sweep_df = sweep_df.sort_values(
            by=["excess_vs_spy", "total_return_pct"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)

    if sweep_df.empty:
        print("No results from sweep.")
        return 1

    print("Top 25 in-sample (by excess vs SPY, then return):")
    print(sweep_df.head(25).to_string(index=False))
    print()

    if args.csv:
        sweep_df.to_csv(args.csv, index=False)
        print(f"Sweep results saved to {args.csv}")
        print()

    if args.oos_start:
        print(f"Out-of-sample: {args.oos_start} → {end} (top {args.top} from in-sample)")
        oos_df = run_oos_validation(
            sweep_df=sweep_df,
            top_n=args.top,
            oos_start=args.oos_start,
            end=end,
            initial_capital=args.capital,
            min_oos_return_pct=args.min_oos_return,
            min_oos_excess_vs_spy=args.min_oos_excess,
        )
        if oos_df.empty:
            print("No OOS results.")
        else:
            print(oos_df.to_string(index=False))
            passed = oos_df["passed"].sum()
            print(f"\nPassed: {passed} / {len(oos_df)}")
            if args.oos_csv:
                oos_df.to_csv(args.oos_csv, index=False)
                print(f"OOS results saved to {args.oos_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

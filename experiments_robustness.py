#!/usr/bin/env python3
"""
Robustness experiments: avoid overfitting to single hot names (e.g. TSLA/NVDA).
- Rank strategies by MEDIAN excess vs SPY across symbols (not mean).
- Diversified portfolio backtest: same strategy on fixed multi-symbol universe, equal weight.
- Multiple OOS splits: does the strategy hold in 2017-2019, 2020-2022, 2023-now?
- Rolling windows: what % of 2-year windows is the strategy profitable / beating B&H?

Usage:
  python3 experiments_robustness.py                    # run all, use sweep_large.csv if present
  python3 experiments_robustness.py --run-sweep       # re-run sweep on fixed universe first
  python3 experiments_robustness.py --no-portfolio    # skip portfolio backtest (faster)
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import numpy as np

from backtest import run_backtest_generic

# Fixed diversified universe (no single-name lottery)
PORTFOLIO_SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "XLK", "XLF"]

# OOS splits: (train_start, train_end, oos_start, oos_end)
OOS_SPLITS = [
    ("2010-01-01", "2016-12-31", "2017-01-01", "2019-12-31"),
    ("2010-01-01", "2019-12-31", "2020-01-01", "2022-12-31"),
    ("2010-01-01", "2022-12-31", "2023-01-01", "2026-12-31"),
]

# Rolling window length (years) and step
ROLLING_YEARS = 2
ROLLING_STEP_YEARS = 1


def _param_key(row: pd.Series, strategy: str) -> tuple:
    if strategy == "sma":
        return (row.get("fast_period"), row.get("slow_period"))
    if strategy == "rsi":
        return (row.get("period"), row.get("oversold"), row.get("overbought"))
    if strategy == "macd":
        return (row.get("fast_ema"), row.get("slow_ema"), row.get("signal_ema"))
    return ()


def _trimmed_median(series: pd.Series, trim_frac: float = 0.1) -> float:
    n = len(series)
    if n == 0:
        return float("nan")
    trim_n = max(0, int(n * trim_frac))
    if trim_n * 2 >= n:
        return series.median()
    trimmed = series.sort_values().iloc[trim_n : n - trim_n]
    return trimmed.median()


def _params_from_row(row: pd.Series, strategy: str) -> dict:
    if strategy == "sma":
        return {"fast_period": int(row["fast_period"]), "slow_period": int(row["slow_period"])}
    if strategy == "rsi":
        return {"period": int(row["period"]), "oversold": float(row["oversold"]), "overbought": float(row["overbought"])}
    if strategy == "macd":
        return {"fast_ema": int(row["fast_ema"]), "slow_ema": int(row["slow_ema"]), "signal_ema": int(row["signal_ema"])}
    return {}


def experiment_median_ranking(sweep_df: pd.DataFrame) -> pd.DataFrame:
    """
    Group by (strategy, params). Compute median(excess_vs_spy), mean(excess), pct with excess > 0.
    Trim extreme symbols: drop top and bottom 10% by excess per (strategy, params) then recompute median.
    """
    sweep_df = sweep_df.dropna(subset=["excess_vs_spy"])
    rows = []
    for strategy, g in sweep_df.groupby("strategy"):
        if strategy == "sma":
            for (fp, sp), gg in g.groupby(["fast_period", "slow_period"]):
                if pd.isna(fp) or pd.isna(sp):
                    continue
                excess = gg["excess_vs_spy"]
                n = len(excess)
                tm = _trimmed_median(excess)
                rows.append({
                    "strategy": strategy,
                    "fast_period": fp, "slow_period": sp,
                    "median_excess": excess.median(),
                    "mean_excess": excess.mean(),
                    "pct_positive": (excess > 0).mean() * 100,
                    "n_symbols": n,
                    "trimmed_median": tm,
                })
        elif strategy == "rsi":
            for (period, oversold, overbought), gg in g.groupby(["period", "oversold", "overbought"]):
                if pd.isna(period):
                    continue
                excess = gg["excess_vs_spy"]
                rows.append({
                    "strategy": strategy,
                    "period": period, "oversold": oversold, "overbought": overbought,
                    "median_excess": excess.median(),
                    "mean_excess": excess.mean(),
                    "pct_positive": (excess > 0).mean() * 100,
                    "n_symbols": len(excess),
                    "trimmed_median": _trimmed_median(excess),
                })
        elif strategy == "macd":
            for (fe, se, sig), gg in g.groupby(["fast_ema", "slow_ema", "signal_ema"]):
                if pd.isna(fe):
                    continue
                excess = gg["excess_vs_spy"]
                rows.append({
                    "strategy": strategy,
                    "fast_ema": fe, "slow_ema": se, "signal_ema": sig,
                    "median_excess": excess.median(),
                    "mean_excess": excess.mean(),
                    "pct_positive": (excess > 0).mean() * 100,
                    "n_symbols": len(excess),
                    "trimmed_median": _trimmed_median(excess),
                })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.sort_values("trimmed_median", ascending=False).reset_index(drop=True)
    return out


def run_portfolio_backtest(
    symbols: list[str],
    start: str,
    end: str,
    strategy: str,
    params: dict,
    initial_capital: float = 100_000.0,
) -> tuple[float, float]:
    """
    Equal-weight portfolio: run backtest on each symbol with capital/n, align equity curves, sum.
    Returns (total_return_pct, max_drawdown_pct).
    """
    cap_per = initial_capital / len(symbols)
    curves = []
    for sym in symbols:
        try:
            eq_df, _, _ = run_backtest_generic(
                symbol=sym, start=start, end=end,
                initial_capital=cap_per, strategy=strategy, **params,
            )
            curves.append(eq_df["equity"])
        except Exception:
            continue
    if not curves:
        return float("nan"), float("nan")
    # Align to common index
    combined = pd.concat(curves, axis=1).ffill().bfill()
    portfolio_equity = combined.sum(axis=1)
    total_return = (portfolio_equity.iloc[-1] / initial_capital - 1.0) * 100
    rolling_max = portfolio_equity.expanding().max()
    drawdown = (portfolio_equity - rolling_max) / rolling_max
    max_dd = drawdown.min() * 100
    return total_return, max_dd


def experiment_portfolio(sweep_df: pd.DataFrame, top_n: int, start: str, end: str) -> pd.DataFrame:
    """Run equal-weight portfolio backtest for top N configs by trimmed_median (from median ranking)."""
    rank_df = experiment_median_ranking(sweep_df)
    if rank_df.empty:
        return pd.DataFrame()
    rank_df = rank_df.head(top_n)
    rows = []
    for _, r in rank_df.iterrows():
        strat = r["strategy"]
        params = _params_from_row(r, strat)
        ret, dd = run_portfolio_backtest(
            PORTFOLIO_SYMBOLS, start, end, strat, params,
        )
        row = {"strategy": strat, "portfolio_return_pct": ret, "portfolio_max_dd_pct": dd}
        for k, v in r.items():
            if k not in row and pd.notna(v):
                row[k] = v
        rows.append(row)
    return pd.DataFrame(rows)


def experiment_multi_oos(candidates_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each candidate (strategy, params), run portfolio backtest on each OOS split.
    Report return and whether beat SPY for each split; pass = profitable in at least 2/3 splits.
    """
    rows = []
    for _, r in candidates_df.iterrows():
        strat = r["strategy"]
        params = _params_from_row(r, strat)
        split_returns = []
        split_spy = []
        for train_s, train_e, oos_s, oos_e in OOS_SPLITS:
            ret, _ = run_portfolio_backtest(
                PORTFOLIO_SYMBOLS, oos_s, oos_e, strat, params,
            )
            split_returns.append(ret)
            # SPY return over same period
            try:
                _, m, _ = run_backtest_generic("SPY", start=oos_s, end=oos_e, strategy=strat, **params)
                spy_ret = m.get("spy_return_pct") or m.get("buy_hold_return_pct")
                split_spy.append(spy_ret)
            except Exception:
                split_spy.append(None)
        n_profitable = sum(1 for x in split_returns if x is not None and not np.isnan(x) and x > 0)
        n_beat_spy = sum(1 for i, x in enumerate(split_returns) if x is not None and split_spy[i] is not None and x > split_spy[i])
        row = {
            "strategy": strat,
            "oos_2017_2019": split_returns[0],
            "oos_2020_2022": split_returns[1],
            "oos_2023_now": split_returns[2],
            "n_profitable_splits": n_profitable,
            "n_beat_spy_splits": n_beat_spy,
            "pass_2of3": n_profitable >= 2,
        }
        for k, v in r.items():
            if k not in row and pd.notna(v):
                row[k] = v
        rows.append(row)
    return pd.DataFrame(rows)


def experiment_rolling_windows(
    strategy: str,
    params: dict,
    symbol: str = "SPY",
    start: str = "2010-01-01",
    end: str = "2025-01-01",
) -> dict:
    """
    Run backtest on overlapping 2-year windows. Return % windows where strategy return > 0 and > B&H.
    """
    from datetime import datetime, timedelta
    start_d = datetime.strptime(start[:10], "%Y-%m-%d")
    end_d = datetime.strptime(end[:10], "%Y-%m-%d")
    wins = []
    t = start_d
    while t + timedelta(days=365 * ROLLING_YEARS) <= end_d:
        w_start = t.strftime("%Y-%m-%d")
        w_end = (t + timedelta(days=365 * ROLLING_YEARS)).strftime("%Y-%m-%d")
        try:
            _, m, _ = run_backtest_generic(symbol, start=w_start, end=w_end, strategy=strategy, **params)
            ret = m["total_return_pct"]
            bh = m["buy_hold_return_pct"]
            wins.append({"return": ret, "buy_hold": bh, "beat_bh": ret > bh if bh is not None else None})
        except Exception:
            pass
        t += timedelta(days=365 * ROLLING_STEP_YEARS)
    if not wins:
        return {"pct_profitable": None, "pct_beat_bh": None, "n_windows": 0}
    returns = [w["return"] for w in wins]
    beat_bh = [w["beat_bh"] for w in wins if w["beat_bh"] is not None]
    return {
        "pct_profitable": 100 * sum(1 for r in returns if r > 0) / len(returns),
        "pct_beat_bh": 100 * sum(beat_bh) / len(beat_bh) if beat_bh else None,
        "n_windows": len(wins),
    }


def main():
    parser = argparse.ArgumentParser(description="Robustness experiments: median ranking, portfolio, multi-OOS")
    parser.add_argument("--sweep-csv", default="sweep_large.csv", help="Sweep results CSV")
    parser.add_argument("--run-sweep", action="store_true", help="Re-run sweep on PORTFOLIO_SYMBOLS before experiments")
    parser.add_argument("--no-portfolio", action="store_true", help="Skip portfolio backtest (faster)")
    parser.add_argument("--top", type=int, default=10, help="Top N configs to test in portfolio and multi-OOS")
    args = parser.parse_args()

    proj = Path(__file__).resolve().parent
    sweep_path = proj / args.sweep_csv

    if args.run_sweep or not sweep_path.is_file():
        print("Running sweep on fixed universe (may take a few minutes)...")
        from backtest_sweep import run_sweep, build_sma_param_grid, build_rsi_param_grid, build_macd_param_grid
        dfs = []
        for strat in ["sma", "rsi", "macd"]:
            if strat == "sma":
                pg = build_sma_param_grid([5, 10, 15, 20], [20, 30, 40, 50])
            elif strat == "rsi":
                pg = build_rsi_param_grid()
            else:
                pg = build_macd_param_grid()
            df = run_sweep(
                symbols=PORTFOLIO_SYMBOLS + ["IWM", "XLE", "XLV"],  # a few more for diversity
                start="2010-01-01",
                end="2024-01-01",
                strategy=strat,
                param_grid=pg,
            )
            if not df.empty:
                dfs.append(df)
        sweep_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        sweep_df = sweep_df.sort_values("excess_vs_spy", ascending=False).reset_index(drop=True)
        sweep_path = proj / "sweep_robustness.csv"
        sweep_df.to_csv(sweep_path, index=False)
        print(f"Saved {sweep_path}")
    else:
        sweep_df = pd.read_csv(sweep_path)
        print(f"Loaded {sweep_path} ({len(sweep_df)} rows)")

    if sweep_df.empty:
        print("No sweep data.")
        return 1

    # 1) Median / consistency ranking (trimmed)
    print("\n=== 1) Rank by MEDIAN excess (trimmed 10% each tail) across symbols ===\n")
    rank_df = experiment_median_ranking(sweep_df)
    print(rank_df.head(15).to_string())
    rank_df.to_csv(proj / "robustness_median_rank.csv", index=False)

    # 2) Portfolio backtest for top configs
    if not args.no_portfolio:
        print("\n=== 2) Equal-weight PORTFOLIO backtest (2010-2024) for top configs ===\n")
        port_df = experiment_portfolio(sweep_df, args.top, "2010-01-01", "2024-12-31")
        print(port_df.to_string())
        port_df.to_csv(proj / "robustness_portfolio.csv", index=False)

    # 3) Multiple OOS splits
    print("\n=== 3) Multiple OOS splits: 2017-19, 2020-22, 2023-now ===\n")
    candidates = rank_df.head(args.top)
    oos_df = experiment_multi_oos(candidates)
    print(oos_df.to_string())
    oos_df.to_csv(proj / "robustness_multi_oos.csv", index=False)

    # 4) Rolling 2-year windows for top 3 configs on SPY
    print("\n=== 4) Rolling 2-year windows on SPY (top 3 by trimmed median) ===\n")
    for i, (_, r) in enumerate(rank_df.head(3).iterrows()):
        strat = r["strategy"]
        params = _params_from_row(r, strat)
        res = experiment_rolling_windows(strat, params, "SPY", "2010-01-01", "2025-01-01")
        print(f"  {strat} {params}: {res['n_windows']} windows, {res['pct_profitable']:.0f}% profitable, {res['pct_beat_bh'] or 0:.0f}% beat B&H")
    print("\nDone. Check robustness_median_rank.csv, robustness_portfolio.csv, robustness_multi_oos.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())

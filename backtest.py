#!/usr/bin/env python3
"""
Backtest momentum (SMA crossover) strategy on historical daily bars.
Uses yfinance for data — no API keys required. Same strategy logic as the live bot.
"""
import argparse
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from strategies.momentum import signals


def run_backtest(
    symbol: str,
    fast_period: int = 10,
    slow_period: int = 30,
    start: str | None = None,
    end: str | None = None,
    initial_capital: float = 100_000.0,
) -> tuple[pd.DataFrame, dict]:
    """
    Run backtest. Returns (equity curve DataFrame, metrics dict).
    """
    if end is None:
        end = datetime.now()
    if start is None:
        start = (datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
    if isinstance(end, datetime):
        end = end.strftime("%Y-%m-%d")

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, auto_adjust=True)
    if df.empty or len(df) < slow_period:
        raise ValueError(f"Not enough data for {symbol} (need at least {slow_period} bars)")

    closes = df["Close"]
    sig = signals(closes, fast_period=fast_period, slow_period=slow_period)

    # Simulate: we get signal at bar i, act at bar i+1 open (no lookahead)
    position = 0  # 0 = flat, 1 = long
    cash = initial_capital
    shares = 0.0
    equity_curve = []
    trades = []

    for i in range(slow_period, len(df)):
        today_open = df["Open"].iloc[i]
        today_close = df["Close"].iloc[i]
        prev_signal = sig.iloc[i - 1] if i > 0 else 0
        curr_signal = sig.iloc[i]

        # Execute at today's open based on previous bar's signal
        if prev_signal > 0 and position == 0:
            # Buy at open
            trades.append({"date": df.index[i], "price": today_open, "side": "buy"})
            shares = cash / today_open
            cash = 0.0
            position = 1
        elif prev_signal < 0 and position == 1:
            # Sell at open
            trades.append({"date": df.index[i], "price": today_open, "side": "sell"})
            cash = shares * today_open
            shares = 0.0
            position = 0

        # Mark-to-market at close for equity
        if position == 1:
            equity = shares * today_close
        else:
            equity = cash
        equity_curve.append({"date": df.index[i], "equity": equity, "position": position})

    eq_df = pd.DataFrame(equity_curve).set_index("date")

    # Strategy metrics
    total_return = (eq_df["equity"].iloc[-1] / initial_capital - 1.0) * 100
    eq_series = eq_df["equity"]
    rolling_max = eq_series.expanding().max()
    drawdown = (eq_series - rolling_max) / rolling_max
    max_drawdown_pct = drawdown.min() * 100
    n_trades = (eq_df["position"].diff().abs() > 0).sum()

    # Buy-and-hold same symbol (same period: first open at slow_period to last close)
    first_open = df["Open"].iloc[slow_period]
    last_close = df["Close"].iloc[-1]
    bh_shares = initial_capital / first_open
    bh_final = bh_shares * last_close
    buy_hold_return_pct = (bh_final / initial_capital - 1.0) * 100
    bh_equity = initial_capital * (df["Close"].iloc[slow_period:] / first_open)
    bh_rolling_max = bh_equity.expanding().max()
    buy_hold_max_dd_pct = ((bh_equity - bh_rolling_max) / bh_rolling_max).min() * 100

    # Buy-and-hold SPY over same calendar period (benchmark)
    spy_start_dt = df.index[slow_period]
    spy_end_dt = df.index[-1]
    spy_start = spy_start_dt.strftime("%Y-%m-%d") if hasattr(spy_start_dt, "strftime") else str(spy_start_dt)[:10]
    spy_end = spy_end_dt.strftime("%Y-%m-%d") if hasattr(spy_end_dt, "strftime") else str(spy_end_dt)[:10]
    if symbol.upper() == "SPY":
        spy_return_pct = buy_hold_return_pct
        spy_max_dd_pct = buy_hold_max_dd_pct
    else:
        spy_ticker = yf.Ticker("SPY")
        spy_df = spy_ticker.history(start=spy_start, end=spy_end, auto_adjust=True)
        if spy_df.empty or len(spy_df) < 2:
            spy_return_pct = spy_max_dd_pct = None
        else:
            spy_first_open = spy_df["Open"].iloc[0]
            spy_last_close = spy_df["Close"].iloc[-1]
            spy_final = initial_capital * (spy_last_close / spy_first_open)
            spy_return_pct = (spy_final / initial_capital - 1.0) * 100
            spy_equity = initial_capital * (spy_df["Close"] / spy_first_open)
            spy_rolling_max = spy_equity.expanding().max()
            spy_max_dd_pct = ((spy_equity - spy_rolling_max) / spy_rolling_max).min() * 100

    metrics = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "fast_period": fast_period,
        "slow_period": slow_period,
        "initial_capital": initial_capital,
        "final_equity": eq_df["equity"].iloc[-1],
        "total_return_pct": total_return,
        "max_drawdown_pct": max_drawdown_pct,
        "n_trades": int(n_trades),
        "buy_hold_return_pct": buy_hold_return_pct,
        "buy_hold_max_dd_pct": buy_hold_max_dd_pct,
        "spy_return_pct": spy_return_pct,
        "spy_max_dd_pct": spy_max_dd_pct,
    }
    return eq_df, metrics


def main():
    parser = argparse.ArgumentParser(description="Backtest SMA crossover on historical data")
    parser.add_argument("symbol", nargs="?", default="SPY", help="Ticker (default: SPY)")
    parser.add_argument("--fast", type=int, default=10, help="Fast SMA period")
    parser.add_argument("--slow", type=int, default=30, help="Slow SMA period")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    parser.add_argument("--csv", metavar="FILE", help="Save equity curve to CSV")
    args = parser.parse_args()

    eq_df, m = run_backtest(
        symbol=args.symbol.upper(),
        fast_period=args.fast,
        slow_period=args.slow,
        start=args.start,
        end=args.end,
        initial_capital=args.capital,
    )

    print(f"Backtest: {m['symbol']} {m['start']} → {m['end']}")
    print(f"  Fast SMA: {m['fast_period']}  Slow SMA: {m['slow_period']}")
    print(f"  Initial capital: ${m['initial_capital']:,.0f}")
    print(f"  Final equity:    ${m['final_equity']:,.2f}")
    print(f"  Total return:    {m['total_return_pct']:.2f}%")
    print(f"  Max drawdown:    {m['max_drawdown_pct']:.2f}%")
    print(f"  Number of trades: {m['n_trades']}")
    print()
    print("  vs buy-and-hold same symbol:")
    print(f"    B&H return:     {m['buy_hold_return_pct']:.2f}%  (strategy: {m['total_return_pct'] - m['buy_hold_return_pct']:+.2f}%)")
    print(f"    B&H max DD:     {m['buy_hold_max_dd_pct']:.2f}%")
    if m.get('spy_return_pct') is not None:
        print("  vs buy-and-hold SPY (same period):")
        print(f"    SPY return:    {m['spy_return_pct']:.2f}%  (strategy: {m['total_return_pct'] - m['spy_return_pct']:+.2f}%)")
        print(f"    SPY max DD:    {m['spy_max_dd_pct']:.2f}%")
    else:
        print("  vs SPY: (same symbol or SPY data unavailable)")

    if args.csv:
        eq_df.to_csv(args.csv)
        print(f"  Equity curve saved to {args.csv}")


if __name__ == "__main__":
    main()

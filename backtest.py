#!/usr/bin/env python3
"""
Backtest strategies (SMA, RSI, MACD) on historical daily bars.
Uses yfinance for data — no API keys required. Same strategy logic as the live bot for SMA.
"""
import argparse
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from strategies import momentum, rsi as rsi_mod, macd as macd_mod

# Strategy registry: name -> (signals_fn, min_bars_fn)
STRATEGIES = {
    "sma": (momentum.signals, momentum.min_bars),
    "rsi": (rsi_mod.signals, rsi_mod.min_bars),
    "macd": (macd_mod.signals, macd_mod.min_bars),
}


def run_backtest_generic(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    initial_capital: float = 100_000.0,
    strategy: str = "sma",
    **strategy_params,
) -> tuple[pd.DataFrame, dict, dict]:
    """
    Run backtest for any registered strategy. Returns (equity curve DataFrame, metrics dict, plot_data dict).
    strategy_params: sma -> fast_period, slow_period; rsi -> period, oversold, overbought; macd -> fast_ema, slow_ema, signal_ema.
    """
    if end is None:
        end = datetime.now()
    if start is None:
        start = (datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
    if isinstance(end, datetime):
        end = end.strftime("%Y-%m-%d")
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}. Choose from {list(STRATEGIES)}")
    signals_fn, min_bars_fn = STRATEGIES[strategy]
    min_bars = min_bars_fn(**strategy_params)
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, auto_adjust=True)
    if df.empty or len(df) < min_bars:
        raise ValueError(f"Not enough data for {symbol} (need at least {min_bars} bars, got {len(df)})")

    closes = df["Close"]
    sig = signals_fn(closes, **strategy_params)

    position = 0
    cash = initial_capital
    shares = 0.0
    equity_curve = []
    trades = []

    for i in range(min_bars, len(df)):
        today_open = df["Open"].iloc[i]
        today_close = df["Close"].iloc[i]
        prev_signal = sig.iloc[i - 1] if i > 0 else 0
        if prev_signal > 0 and position == 0:
            trades.append({"date": df.index[i], "price": today_open, "side": "buy"})
            shares = cash / today_open
            cash = 0.0
            position = 1
        elif prev_signal < 0 and position == 1:
            trades.append({"date": df.index[i], "price": today_open, "side": "sell"})
            cash = shares * today_open
            shares = 0.0
            position = 0
        equity = shares * today_close if position == 1 else cash
        equity_curve.append({"date": df.index[i], "equity": equity, "position": position})

    eq_df = pd.DataFrame(equity_curve).set_index("date")
    total_return = (eq_df["equity"].iloc[-1] / initial_capital - 1.0) * 100
    eq_series = eq_df["equity"]
    rolling_max = eq_series.expanding().max()
    drawdown = (eq_series - rolling_max) / rolling_max
    max_drawdown_pct = drawdown.min() * 100
    n_trades = (eq_df["position"].diff().abs() > 0).sum()

    first_open = df["Open"].iloc[min_bars]
    last_close = df["Close"].iloc[-1]
    bh_shares = initial_capital / first_open
    bh_final = bh_shares * last_close
    buy_hold_return_pct = (bh_final / initial_capital - 1.0) * 100
    bh_equity = initial_capital * (df["Close"].iloc[min_bars:] / first_open)
    bh_rolling_max = bh_equity.expanding().max()
    buy_hold_max_dd_pct = ((bh_equity - bh_rolling_max) / bh_rolling_max).min() * 100

    spy_start_dt = df.index[min_bars]
    spy_end_dt = df.index[-1]
    spy_start = spy_start_dt.strftime("%Y-%m-%d") if hasattr(spy_start_dt, "strftime") else str(spy_start_dt)[:10]
    spy_end = spy_end_dt.strftime("%Y-%m-%d") if hasattr(spy_end_dt, "strftime") else str(spy_end_dt)[:10]
    spy_df = None
    if symbol.upper() == "SPY":
        spy_return_pct = buy_hold_return_pct
        spy_max_dd_pct = buy_hold_max_dd_pct
    else:
        spy_ticker = yf.Ticker("SPY")
        spy_df = spy_ticker.history(start=spy_start, end=spy_end, auto_adjust=True)
        if spy_df.empty or len(spy_df) < 2:
            spy_return_pct = spy_max_dd_pct = None
            spy_df = None
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
        "strategy": strategy,
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
    metrics.update(strategy_params)

    close_slice = closes.iloc[min_bars:]
    strategy_pct = (eq_df["equity"] / initial_capital - 1.0) * 100
    bh_pct = (bh_equity / initial_capital - 1.0) * 100
    if symbol.upper() == "SPY":
        spy_pct = bh_pct.copy()
    elif spy_df is not None:
        spy_close_aligned = spy_df["Close"].reindex(eq_df.index, method="ffill").bfill()
        spy_pct = (spy_close_aligned / spy_close_aligned.iloc[0] - 1.0) * 100
    else:
        spy_pct = None
    plot_data = {
        "close": close_slice,
        "trades": trades,
        "strategy_pct": strategy_pct,
        "bh_pct": bh_pct,
        "spy_pct": spy_pct,
    }
    if strategy == "sma":
        from strategies.momentum import sma
        plot_data["fast_sma"] = sma(closes, strategy_params["fast_period"]).iloc[min_bars:]
        plot_data["slow_sma"] = sma(closes, strategy_params["slow_period"]).iloc[min_bars:]
    return eq_df, metrics, plot_data


def run_backtest(
    symbol: str,
    fast_period: int = 10,
    slow_period: int = 30,
    start: str | None = None,
    end: str | None = None,
    initial_capital: float = 100_000.0,
) -> tuple[pd.DataFrame, dict, dict]:
    """Run backtest for SMA strategy (backward-compatible)."""
    return run_backtest_generic(
        symbol=symbol,
        start=start,
        end=end,
        initial_capital=initial_capital,
        strategy="sma",
        fast_period=fast_period,
        slow_period=slow_period,
    )


def plot_backtest(plot_data: dict, symbol: str, metrics: dict, save_path: str) -> None:
    """
    Generate a two-panel plot: price + SMAs + buy/sell markers, and cumulative % returns (strategy vs B&H symbol vs SPY).
    Saves to save_path. Uses Agg backend for headless use.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    close = plot_data["close"]
    trades = plot_data["trades"]
    strategy_pct = plot_data["strategy_pct"]
    bh_pct = plot_data["bh_pct"]
    spy_pct = plot_data.get("spy_pct")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    # Top: price + optional SMAs + buy/sell
    ax1.plot(close.index, close.values, label="Close", color="black", alpha=0.8)
    if "fast_sma" in plot_data and "slow_sma" in plot_data:
        ax1.plot(plot_data["fast_sma"].index, plot_data["fast_sma"].values, label=f"SMA {metrics.get('fast_period', '')}", color="green", alpha=0.8)
        ax1.plot(plot_data["slow_sma"].index, plot_data["slow_sma"].values, label=f"SMA {metrics.get('slow_period', '')}", color="blue", alpha=0.8)
    buys = [t for t in trades if t["side"] == "buy"]
    sells = [t for t in trades if t["side"] == "sell"]
    if buys:
        ax1.scatter(
            [t["date"] for t in buys],
            [t["price"] for t in buys],
            marker="^",
            color="green",
            s=80,
            zorder=5,
            label="Buy",
        )
    if sells:
        ax1.scatter(
            [t["date"] for t in sells],
            [t["price"] for t in sells],
            marker="v",
            color="red",
            s=80,
            zorder=5,
            label="Sell",
        )
    ax1.set_title(f"{symbol} — {metrics.get('strategy', 'SMA')} ({metrics['start']} → {metrics['end']})")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel("Price ($)")

    # Bottom: cumulative % return — strategy, buy & hold symbol, SPY
    ax2.plot(strategy_pct.index, strategy_pct.values, label="Strategy", color="black", alpha=0.8)
    ax2.plot(bh_pct.index, bh_pct.values, label=f"Buy & hold {symbol}", color="blue", alpha=0.8)
    if spy_pct is not None and symbol.upper() != "SPY":
        ax2.plot(spy_pct.index, spy_pct.values, label="SPY", color="gray", alpha=0.8)
    ax2.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax2.set_ylabel("Cumulative return (%)")
    ax2.set_title("Cumulative % return")
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(save_path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Backtest SMA crossover on historical data")
    parser.add_argument("symbol", nargs="?", default="SPY", help="Ticker (default: SPY)")
    parser.add_argument("--fast", type=int, default=10, help="Fast SMA period")
    parser.add_argument("--slow", type=int, default=30, help="Slow SMA period")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    parser.add_argument("--csv", metavar="FILE", help="Save equity curve to CSV")
    parser.add_argument("--plot", action="store_true", help="Save backtest plot to file")
    parser.add_argument("--plot-out", metavar="FILE", default=None, help="Plot output path (default: backtest_<SYMBOL>.png)")
    args = parser.parse_args()

    eq_df, m, plot_data = run_backtest(
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

    if args.plot:
        path = args.plot_out or f"backtest_{m['symbol']}.png"
        plot_backtest(plot_data, m["symbol"], m, save_path=path)
        print(f"  Plot saved to {path}")


if __name__ == "__main__":
    main()

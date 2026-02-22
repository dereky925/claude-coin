"""
Shared helpers for daily report, status report, and Telegram command bot.
Fetches bars from Alpaca (IEX), builds SMA plots, formats account status.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass
_env_dir = Path(__file__).resolve().parent
_env_file = _env_dir / ".env"
if _env_file.is_file():
    try:
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\r")
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip().strip("\r")
                    if key and os.environ.get(key) in (None, ""):
                        os.environ[key] = value
    except Exception:
        pass


def get_bars(data_client, symbol: str, slow_period: int):
    """Daily bars for symbol (same as bot). Returns pandas Series of closes or None."""
    import pandas as pd
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=slow_period + 90)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    bars = data_client.get_stock_bars(req)
    if not bars or symbol not in bars.data or not bars.data[symbol]:
        return None
    close_series = pd.Series(
        {b.timestamp: b.close for b in bars.data[symbol]},
        dtype=float,
    ).sort_index()
    return close_series


def get_account_status(trading_client) -> str:
    """Full account + positions text (same logic as bot's _account_summary)."""
    try:
        account = trading_client.get_account()
        equity = float(account.equity or 0)
        cash = float(account.cash or 0)
        last_equity = float(account.last_equity or 0)
        daily_change = equity - last_equity if last_equity else 0
        daily_str = f"${daily_change:+,.2f}" if last_equity else "—"
        lines = [
            f"Equity: ${equity:,.2f}",
            f"Cash:   ${cash:,.2f}",
            f"Today:  {daily_str}",
        ]
        try:
            positions = trading_client.get_all_positions()
        except Exception:
            positions = []
        if positions:
            lines.append("")
            lines.append("Positions:")
            for pos in positions:
                qty = float(pos.qty or 0)
                upl = float(pos.unrealized_pl or 0)
                sym = getattr(pos, "symbol", None) or getattr(pos, "symbol_id", "?")
                lines.append(f"  {sym}: {qty:.0f} sh  P&L ${upl:+,.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not load account: {e}"


def get_signals_text(data_client, symbols: list, fast_period: int, slow_period: int) -> str:
    """Current signal (buy/sell/hold) per symbol."""
    from strategies.momentum import signal_at_end

    lines = ["Current signals:"]
    for symbol in symbols:
        closes = get_bars(data_client, symbol, slow_period)
        if closes is None or len(closes) < slow_period:
            lines.append(f"  {symbol}: (no data)")
            continue
        signal = signal_at_end(closes, fast_period=fast_period, slow_period=slow_period)
        lines.append(f"  {symbol}: {signal.upper()}")
    return "\n".join(lines)


def build_sma_plot(closes, symbol: str, fast_period: int, slow_period: int) -> str | None:
    """
    Plot close + fast SMA + slow SMA. Saves to a temp PNG file.
    Returns path to the file, or None on error. Caller must delete the file.
    """
    import pandas as pd

    from strategies.momentum import sma

    if closes is None or len(closes) < slow_period:
        return None
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(closes.index, closes.values, label="Close", color="black", alpha=0.8)
    ax.plot(fast.index, fast.values, label=f"SMA {fast_period}", color="green", alpha=0.8)
    ax.plot(slow.index, slow.values, label=f"SMA {slow_period}", color="blue", alpha=0.8)
    ax.set_title(f"{symbol} — Price & SMAs")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    fig.savefig(tmp.name, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return tmp.name

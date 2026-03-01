"""
MACD strategy: buy when MACD line crosses above signal line, sell when below.
Reusable for backtesting; same signals interface as momentum.
"""
from typing import List, Union

import pandas as pd


def ema(series: Union[pd.Series, List[float]], period: int) -> pd.Series:
    """Exponential moving average."""
    if isinstance(series, list):
        series = pd.Series(series)
    return series.ewm(span=period, adjust=False).mean()


def signals(
    closes: Union[pd.Series, List[float]],
    fast_ema: int = 12,
    slow_ema: int = 26,
    signal_ema: int = 9,
) -> pd.Series:
    """
    Crossover signals: 1 = buy (MACD crosses above signal), -1 = sell (MACD crosses below signal), 0 = hold.
    First (slow_ema + signal_ema) bars are NaN (no signal).
    """
    if isinstance(closes, list):
        closes = pd.Series(closes)
    ema_fast = ema(closes, fast_ema)
    ema_slow = ema(closes, slow_ema)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal_ema)
    prev_macd = macd_line.shift(1)
    prev_sig = signal_line.shift(1)
    # Buy when MACD crosses above signal
    buy = (prev_macd <= prev_sig) & (macd_line > signal_line)
    # Sell when MACD crosses below signal
    sell = (prev_macd >= prev_sig) & (macd_line < signal_line)
    raw = pd.Series(0, index=closes.index, dtype=int)
    raw.loc[buy] = 1
    raw.loc[sell] = -1
    return raw.reindex(closes.index).fillna(0).astype(int)


def signal_at_end(
    closes: Union[pd.Series, List[float]],
    fast_ema: int = 12,
    slow_ema: int = 26,
    signal_ema: int = 9,
) -> str:
    """Single signal for the latest bar only. Returns 'buy', 'sell', or 'hold'."""
    s = signals(closes, fast_ema=fast_ema, slow_ema=slow_ema, signal_ema=signal_ema)
    if s.empty or pd.isna(s.iloc[-1]):
        return "hold"
    v = int(s.iloc[-1])
    if v > 0:
        return "buy"
    if v < 0:
        return "sell"
    return "hold"


def min_bars(fast_ema: int = 12, slow_ema: int = 26, signal_ema: int = 9, **kwargs) -> int:
    """Minimum bars needed before first signal."""
    return slow_ema + signal_ema

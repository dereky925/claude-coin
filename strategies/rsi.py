"""
RSI strategy: buy when RSI crosses above oversold (30), sell when crosses below overbought (70).
Reusable for backtesting; same signals interface as momentum.
"""
from typing import List, Union

import pandas as pd


def rsi(series: Union[pd.Series, List[float]], period: int = 14) -> pd.Series:
    """Relative Strength Index. Returns NaN until period+1 bars."""
    if isinstance(series, list):
        series = pd.Series(series)
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return (100 - (100 / (1 + rs))).fillna(50)


def signals(
    closes: Union[pd.Series, List[float]],
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> pd.Series:
    """
    Crossover signals: 1 = buy (RSI crosses above oversold), -1 = sell (RSI crosses below overbought), 0 = hold.
    First (period) bars are NaN (no signal).
    """
    if isinstance(closes, list):
        closes = pd.Series(closes)
    r = rsi(closes, period)
    prev_r = r.shift(1)
    # Buy when RSI crosses above oversold (exiting oversold)
    buy = (prev_r <= oversold) & (r > oversold)
    # Sell when RSI crosses below overbought (exiting overbought)
    sell = (prev_r >= overbought) & (r < overbought)
    raw = pd.Series(0, index=closes.index, dtype=int)
    raw.loc[buy] = 1
    raw.loc[sell] = -1
    return raw.reindex(closes.index).fillna(0).astype(int)


def signal_at_end(
    closes: Union[pd.Series, List[float]],
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> str:
    """Single signal for the latest bar only. Returns 'buy', 'sell', or 'hold'."""
    s = signals(closes, period=period, oversold=oversold, overbought=overbought)
    if s.empty or pd.isna(s.iloc[-1]):
        return "hold"
    v = int(s.iloc[-1])
    if v > 0:
        return "buy"
    if v < 0:
        return "sell"
    return "hold"


def min_bars(period: int = 14, **kwargs) -> int:
    """Minimum bars needed before first signal."""
    return period + 1

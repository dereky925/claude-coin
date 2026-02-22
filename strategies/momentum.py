"""
Momentum strategy: moving-average crossover.
Reusable for backtesting and live bot — same logic, different data source.
"""
from typing import List, Union

import pandas as pd


def sma(series: Union[pd.Series, List[float]], period: int) -> pd.Series:
    """Simple moving average. Returns NaN for first (period - 1) bars."""
    if isinstance(series, list):
        series = pd.Series(series)
    return series.rolling(window=period, min_periods=period).mean()


def signals(
    closes: Union[pd.Series, List[float]],
    fast_period: int = 10,
    slow_period: int = 30,
) -> pd.Series:
    """
    Crossover signals: 1 = buy (fast > slow), -1 = sell (fast < slow), 0 = hold.
    Uses close price. First (slow_period - 1) bars are NaN (no signal).
    """
    if isinstance(closes, list):
        closes = pd.Series(closes)
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)
    # 1 = bullish, -1 = bearish, 0 = no clear signal (e.g. equal)
    raw = (fast > slow).astype(int) - (fast < slow).astype(int)
    return raw.reindex(closes.index).fillna(0).astype(int)


def signal_at_end(
    closes: Union[pd.Series, List[float]],
    fast_period: int = 10,
    slow_period: int = 30,
) -> str:
    """
    Single signal for the latest bar only. For use by live bot.
    Returns "buy", "sell", or "hold".
    """
    s = signals(closes, fast_period, slow_period)
    if s.empty or pd.isna(s.iloc[-1]):
        return "hold"
    v = int(s.iloc[-1])
    if v > 0:
        return "buy"
    if v < 0:
        return "sell"
    return "hold"

"""
Orchestrates Tavily (news) + Gemini (advisory) for the trading bot.
"""
from __future__ import annotations

from typing import List, Optional

from agent.tavily_client import search_market_news_with_usage
from agent.gemini_client import get_agent_action as _get_agent_action_impl


def get_agent_action(
    symbol: str,
    technical_signal: str,
    last_close: float,
    position_qty: float,
    use_agent: bool = True,
    news_snippets_override: Optional[List[dict]] = None,
    general_snippets_override: Optional[List[dict]] = None,
) -> dict:
    """
    Get advisory action for a potential trade. Returns dict with action, reason,
    news (list), and usage (gemini + tavily). If general_snippets_override is
    provided (hybrid), combines with symbol news for context.
    """
    if not use_agent:
        return {"action": "confirm", "reason": "agent disabled", "news": [], "usage": {}}

    snippets = news_snippets_override
    tavily_usage = {}
    if snippets is None:
        snippets, tavily_usage = search_market_news_with_usage(symbol)

    combined = list(snippets) if snippets else []
    if general_snippets_override:
        combined = list(general_snippets_override) + combined

    result = _get_agent_action_impl(
        symbol=symbol,
        technical_signal=technical_signal,
        last_close=last_close,
        position_qty=position_qty,
        news_snippets=combined[:10],
    )
    result["news"] = combined[:10]
    g_usage = result.pop("usage", None)
    result["usage"] = {}
    if g_usage:
        result["usage"]["gemini"] = g_usage
    if tavily_usage:
        result["usage"]["tavily"] = tavily_usage
    return result

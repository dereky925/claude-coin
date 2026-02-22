"""
Orchestrates Tavily (news) + Gemini (advisory) for the trading bot.
"""
from __future__ import annotations

from typing import List, Optional

from agent.tavily_client import search_market_news
from agent.gemini_client import get_agent_action as _get_agent_action_impl


def get_agent_action(
    symbol: str,
    technical_signal: str,
    last_close: float,
    position_qty: float,
    use_agent: bool = True,
    news_snippets_override: Optional[List[dict]] = None,
) -> dict:
    """
    Get advisory action for a potential trade. If use_agent is False, returns
    {"action": "confirm", "reason": "agent disabled"}.
    Otherwise fetches news via Tavily, then calls Gemini; returns dict with
    action ("confirm"|"reduce"|"skip"|"override_sell") and reason.
    """
    if not use_agent:
        return {"action": "confirm", "reason": "agent disabled"}

    snippets = news_snippets_override
    if snippets is None:
        snippets = search_market_news(symbol)

    return _get_agent_action_impl(
        symbol=symbol,
        technical_signal=technical_signal,
        last_close=last_close,
        position_qty=position_qty,
        news_snippets=snippets,
    )

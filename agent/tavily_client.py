"""
Tavily client for market/news search. Used by the agentic layer.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass


def _get_api_key() -> Optional[str]:
    return os.getenv("TAVILY_API_KEY") or None


def search_market_news(symbol: str, query_override: Optional[str] = None) -> list:
    """Search for recent market/symbol news. Returns list of dicts with title, url, snippet.
    For usage/credits use search_market_news_with_usage."""
    results, _ = search_market_news_with_usage(symbol, query_override)
    return results


def search_market_news_with_usage(
    symbol: str, query_override: Optional[str] = None
) -> tuple[list, dict]:
    """
    Search for recent market/symbol news. Returns (list of dicts, usage_dict).
    usage_dict has "credits" when include_usage=True. Returns ([], {}) on error.
    """
    api_key = _get_api_key()
    if not api_key:
        return [], {}

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        query = query_override or f"{symbol} stock news market"
        response = client.search(
            query=query,
            topic="news",
            max_results=5,
            search_depth="basic",
            include_answer=False,
            time_range="week",
            include_usage=True,
        )
        raw = getattr(response, "results", None)
        if raw is None and isinstance(response, dict):
            raw = response.get("results", [])
        results = raw or []
        out = []
        for r in results:
            def _v(obj, key):
                if hasattr(obj, key):
                    return getattr(obj, key) or ""
                if isinstance(obj, dict):
                    return obj.get(key) or ""
                return ""
            snippet = _v(r, "content") or _v(r, "snippet")
            out.append({"title": _v(r, "title"), "url": _v(r, "url"), "snippet": snippet})
        usage = {}
        u = getattr(response, "usage", None) or (response.get("usage") if isinstance(response, dict) else None)
        if u is not None:
            if hasattr(u, "total_credits_used"):
                usage["credits"] = getattr(u, "total_credits_used", None)
            elif isinstance(u, dict):
                usage["credits"] = u.get("total_credits_used") or u.get("credits")
        return out, usage
    except Exception as e:
        _log.warning("Tavily search failed: %s", e, exc_info=True)
        return [], {}


def search_market_news_general() -> tuple[list, dict]:
    """One general market news search (e.g. for hybrid mode). Returns (list of dicts, usage_dict)."""
    return search_market_news_with_usage("SPY", query_override="US stock market S&P 500 news today")

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
    """
    Search for recent market/symbol news. Returns list of dicts with title, url, snippet.
    Uses topic=finance and a short time range. Returns [] on missing key or API error.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

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
        return out
    except Exception as e:
        _log.warning("Tavily search failed: %s", e, exc_info=True)
        return []

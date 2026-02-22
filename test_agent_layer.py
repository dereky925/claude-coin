#!/usr/bin/env python3
"""
Test script for the agentic layer: Tavily and Gemini connectivity and full agent path.
Run from project root: python test_agent_layer.py
Use --verbose to print Tavily raw response shape for debugging.
"""
import argparse
import os
import sys
from pathlib import Path

# Load .env like bot.py
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.is_file():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\r")
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip().strip("\r")
                    if key and os.environ.get(key) in (None, ""):
                        os.environ[key] = value


def test_tavily(verbose: bool = False):
    """Test Tavily API: search for SPY news and print results."""
    from agent.tavily_client import search_market_news, _get_api_key

    if not _get_api_key():
        print("TAVILY: SKIP (TAVILY_API_KEY not set)")
        return True

    if verbose:
        _run_tavily_verbose()
        return True

    try:
        results = search_market_news("SPY")
        if not results:
            print("TAVILY: WARN no results (check key or network)")
            print("  Hint: Check TAVILY_API_KEY and network; see logs for 'Tavily search failed' if configured.")
        else:
            print(f"TAVILY: OK ({len(results)} results)")
            for i, r in enumerate(results[:2], 1):
                print(f"  {i}. {r.get('title', '')[:60]}...")
        return True
    except Exception as e:
        print(f"TAVILY: FAIL {e}")
        return False


def _run_tavily_verbose():
    """Print raw Tavily response shape for debugging (type, results, len, first result)."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("TAVILY verbose: TAVILY_API_KEY not set")
        return
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(
            "SPY stock news market",
            topic="news",
            max_results=5,
            search_depth="basic",
            include_answer=False,
            time_range="week",
        )
        raw_results = getattr(response, "results", None)
        if raw_results is None and isinstance(response, dict):
            raw_results = response.get("results", [])
        results_list = raw_results or []
        print("TAVILY verbose: type(response) =", type(response).__name__)
        print("TAVILY verbose: getattr(response, 'results', N/A) =", type(raw_results).__name__ if raw_results is not None else "N/A")
        print("TAVILY verbose: len(results) =", len(results_list))
        if results_list:
            r0 = results_list[0]
            keys = list(r0.keys()) if isinstance(r0, dict) else list(getattr(r0, "__dict__", dir(r0)))
            print("TAVILY verbose: first result keys =", keys[:15] if len(keys) > 15 else keys)
            title = getattr(r0, "title", None) or (r0.get("title") if isinstance(r0, dict) else None)
            print("TAVILY verbose: first result title =", (title or "")[:80])
        else:
            print("TAVILY verbose: no results in response")
    except Exception as e:
        print("TAVILY verbose: exception =", e)
        import traceback
        traceback.print_exc()


def test_gemini():
    """Test Gemini API: trivial prompt and check non-empty response."""
    from agent.gemini_client import _get_api_key, _get_model

    if not _get_api_key():
        print("GEMINI: SKIP (GEMINI_API_KEY not set)")
        return True

    try:
        from google import genai
        client = genai.Client(api_key=_get_api_key())
        model = _get_model()
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly the word OK and nothing else.",
        )
        text = (getattr(response, "text", None) or "").strip()
        if text:
            print(f"GEMINI: OK (model={model}, response={text[:50]!r})")
        else:
            print("GEMINI: WARN empty response")
        return True
    except Exception as e:
        print(f"GEMINI: FAIL {e}")
        return False


def test_agent_integration():
    """Test full agent: get_agent_action with mock inputs."""
    from agent.agent import get_agent_action
    from agent.gemini_client import VALID_ACTIONS

    try:
        result = get_agent_action(
            symbol="SPY",
            technical_signal="buy",
            last_close=500.0,
            position_qty=0.0,
            use_agent=True,
        )
        action = result.get("action")
        reason = result.get("reason", "")
        if action not in VALID_ACTIONS:
            print(f"AGENT: FAIL invalid action {action!r}")
            return False
        print(f"AGENT: OK action={action!r} reason={reason[:60]!r}...")
        return True
    except Exception as e:
        print(f"AGENT: FAIL {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test agentic layer (Tavily + Gemini)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print Tavily raw response shape for debugging")
    args = parser.parse_args()

    print("Testing agentic layer (Tavily + Gemini)...")
    ok_t = test_tavily(verbose=args.verbose)
    ok_g = test_gemini()
    ok_a = test_agent_integration()
    if ok_t and ok_g and ok_a:
        print("All checks passed.")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()

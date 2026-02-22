"""
Gemini client for advisory actions. Used by the agentic layer.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

DEFAULT_MODEL = "gemini-2.5-flash"
VALID_ACTIONS = frozenset({"confirm", "reduce", "skip", "override_sell"})


def _get_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or None


def _get_model() -> str:
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def _parse_action_response(text: str) -> dict:
    """Parse ACTION: x and REASON: y from model output. Returns dict with action, reason."""
    action = "skip"
    reason = "could not parse agent response"
    if not text or not isinstance(text, str):
        return {"action": action, "reason": reason}

    text = text.strip()
    action_match = re.search(r"ACTION:\s*(\w+)", text, re.IGNORECASE)
    if action_match:
        raw = action_match.group(1).strip().lower()
        if raw in VALID_ACTIONS:
            action = raw

    reason_match = re.search(r"REASON:\s*(.+?)(?=\n\n|\nACTION:|$)", text, re.IGNORECASE | re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip() or reason

    return {"action": action, "reason": reason}


def get_agent_action(
    symbol: str,
    technical_signal: str,
    last_close: float,
    position_qty: float,
    news_snippets: list[dict],
) -> dict:
    """
    Call Gemini with symbol, technical signal, price, position, and news. Returns
    dict with keys: action ("confirm"|"reduce"|"skip"|"override_sell"), reason (str).
    On API/parse failure returns {"action": "skip", "reason": "agent error"}.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"action": "skip", "reason": "GEMINI_API_KEY not set"}

    model = _get_model()
    news_blob = "\n".join(
        f"- {s.get('title', '')}: {s.get('snippet', '')[:300]}"
        for s in (news_snippets or [])[:5]
    ) or "No recent news found."

    system = (
        "You are a trading advisor. You receive a technical signal (buy/sell) and recent news. "
        "Reply with exactly two lines: ACTION: <one of confirm, reduce, skip, override_sell> "
        "then REASON: <short explanation>. confirm = trust the signal at full size. "
        "reduce = trust but use half size. skip = do not trade this bar. "
        "override_sell = disagree with a buy (skip the buy) or suggest selling if long. "
        "Use only the words confirm, reduce, skip, or override_sell for ACTION."
    )
    user = (
        f"Symbol: {symbol}. Technical signal: {technical_signal}. Last close: {last_close}. "
        f"Current position qty: {position_qty}. Recent news:\n{news_blob}\n\n"
        "Reply with ACTION: <word> then REASON: <explanation>."
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        combined = f"{system}\n\n{user}"
        response = client.models.generate_content(
            model=model,
            contents=combined,
        )
        text = getattr(response, "text", None) or ""
        out = _parse_action_response(text)
        um = getattr(response, "usage_metadata", None)
        if um is not None:
            pin = getattr(um, "prompt_token_count", None) or getattr(um, "input_token_count", None) or 0
            pout = getattr(um, "candidates_token_count", None) or getattr(um, "output_token_count", None) or 0
            out["usage"] = {
                "prompt_tokens": pin,
                "output_tokens": pout,
                "total_tokens": getattr(um, "total_token_count", None) or (pin + pout),
                "estimated_usd": (pin / 1e6 * 0.30) + (pout / 1e6 * 2.50),
            }
        return out
    except Exception as e:
        return {"action": "skip", "reason": f"agent error: {e}"}

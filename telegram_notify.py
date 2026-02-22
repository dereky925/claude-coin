"""
Send messages to Telegram. Used by the trading bot for trade alerts and errors.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

def _load_env():
    """Load .env from script directory (handles paths with spaces and CRLF)."""
    script_dir = Path(__file__).resolve().parent
    try:
        from dotenv import load_dotenv
        load_dotenv(script_dir / ".env")
        load_dotenv(".env")
    except Exception:
        pass
    # Fallback: parse .env ourselves (dotenv can fail with path spaces / CRLF)
    for name in (".env", ".env.local"):
        path = script_dir / name
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip().strip("\r")
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key, value = key.strip().strip("\r"), value.strip().strip("\r")
                        if key and os.environ.get(key) in (None, ""):
                            os.environ[key] = value
        except Exception:
            pass


_load_env()


def _is_configured() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return bool(token and chat_id)


def send_message(text: str) -> bool:
    """
    Send a text message to the configured Telegram chat.
    Returns True if sent, False if not configured or on error.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def notify_trade(
    symbol: str,
    side: str,
    qty: int | float,
    order_id: str,
    paper: bool,
    *,
    pnl_dollars: float | None = None,
    account_summary: str | None = None,
) -> None:
    mode = "paper" if paper else "LIVE"
    msg = f"🔄 {mode} {side.upper()} {symbol} qty={qty} order_id={order_id}"
    if pnl_dollars is not None:
        sign = "+" if pnl_dollars >= 0 else ""
        msg += f"\n  P&L: {sign}${pnl_dollars:.2f}"
    if account_summary:
        msg += f"\n\n{account_summary}"
    send_message(msg)


def notify_account_status(summary: str) -> None:
    """Send account status (equity, cash, positions)."""
    send_message(f"📊 Account\n\n{summary}")


def notify_error(message: str) -> None:
    send_message(f"❌ Bot error: {message}")


if __name__ == "__main__":
    """Send a test message to verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."""
    env_path = Path(__file__).resolve().parent / ".env"
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _is_configured():
        print("Not configured. In .env add (no quotes, no spaces around =):")
        print("  TELEGRAM_BOT_TOKEN=your_token_from_botfather")
        print("  TELEGRAM_CHAT_ID=your_chat_id")
        if not token:
            print("  -> TELEGRAM_BOT_TOKEN is missing or empty")
        if not chat_id:
            print("  -> TELEGRAM_CHAT_ID is missing or empty")
        print(f"  (Loading .env from: {env_path})")
        exit(1)
    ok = send_message("✅ Claude Coin Telegram test — if you see this, alerts will work.")
    print("Sent." if ok else "Failed to send (check token and chat_id).")
    exit(0 if ok else 1)

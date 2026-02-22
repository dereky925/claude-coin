#!/usr/bin/env python3
"""
Long-poll Telegram for commands. When you send /report or /status to your bot,
replies with current status + SMA charts. /start, /stop, /restart control PM2.
Run in background or PM2: python3 telegram_commands.py
Only the chat_id in .env can trigger commands.
"""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass
_env_dir = Path(__file__).resolve().parent
_env_file = _env_dir / ".env"
if _env_file.is_file():
    try:
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\r")
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip().strip("\r")
                    if key and os.environ.get(key) in (None, ""):
                        os.environ[key] = value
    except Exception:
        pass


# Reused Alpaca clients for /report and /status (avoids allocating new clients per run)
_report_trading_client = None
_report_data_client = None


def _get_report_clients():
    """Return (trading_client, data_client) for status reports, reusing one pair per process."""
    global _report_trading_client, _report_data_client
    if _report_trading_client is None or _report_data_client is None:
        from alpaca_client import get_data_client, get_trading_client
        paper_raw = os.getenv("BOT_PAPER", os.getenv("APCA_PAPER", "true")).lower()
        paper = paper_raw in ("true", "1", "yes")
        _report_trading_client = get_trading_client(paper=paper)
        _report_data_client = get_data_client()
    return _report_trading_client, _report_data_client


def _pm2_bot_app_name() -> str:
    return os.getenv("PM2_BOT_APP_NAME", "claude-coin-bot").strip() or "claude-coin-bot"


def _pm2_cwd() -> Path:
    cwd = os.getenv("BOT_CWD", "").strip() or os.getenv("PM2_CWD", "").strip()
    if cwd:
        return Path(cwd)
    return Path(__file__).resolve().parent


def _run_pm2_start_bot() -> tuple[bool, str]:
    """Run pm2 start <bot_app_name> then pm2 save. Does NOT start ecosystem (avoids restarting this process)."""
    name = _pm2_bot_app_name()
    try:
        r1 = subprocess.run(
            ["pm2", "start", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r1.returncode != 0:
            return False, (r1.stderr or r1.stdout or "pm2 start failed").strip()[:200]
        r2 = subprocess.run(
            ["pm2", "save"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True, "Claude Coin Bot started and saved."
    except subprocess.TimeoutExpired:
        return False, "pm2 timed out"
    except FileNotFoundError:
        return False, "pm2 not found (install PM2)"
    except Exception as e:
        return False, str(e)[:200]


def _run_pm2_start_ecosystem() -> tuple[bool, str]:
    """Run pm2 start ecosystem.config.cjs then pm2 save. WARNING: restarts telegram-commands too (use from shell only)."""
    cwd = _pm2_cwd()
    ecosystem = cwd / "ecosystem.config.cjs"
    if not ecosystem.is_file():
        return False, "ecosystem.config.cjs not found"
    try:
        r1 = subprocess.run(
            ["pm2", "start", "ecosystem.config.cjs"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r1.returncode != 0:
            return False, (r1.stderr or r1.stdout or "pm2 start failed").strip()[:200]
        r2 = subprocess.run(
            ["pm2", "save"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True, "Started (ecosystem) and saved."
    except subprocess.TimeoutExpired:
        return False, "pm2 timed out"
    except FileNotFoundError:
        return False, "pm2 not found (install PM2)"
    except Exception as e:
        return False, str(e)[:200]


def _run_pm2_stop_bot() -> tuple[bool, str]:
    """Run pm2 stop <bot_app_name>. Return (ok, message)."""
    name = _pm2_bot_app_name()
    try:
        r = subprocess.run(
            ["pm2", "stop", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "pm2 stop failed").strip()[:200]
        return True, "Claude Coin Bot stopped."
    except subprocess.TimeoutExpired:
        return False, "pm2 timed out"
    except FileNotFoundError:
        return False, "pm2 not found (install PM2)"
    except Exception as e:
        return False, str(e)[:200]


def _run_pm2_restart_bot() -> tuple[bool, str]:
    """Run pm2 restart <bot_app_name>. Return (ok, message)."""
    name = _pm2_bot_app_name()
    try:
        r = subprocess.run(
            ["pm2", "restart", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "pm2 restart failed").strip()[:200]
        return True, "Claude Coin Bot restarting."
    except subprocess.TimeoutExpired:
        return False, "pm2 timed out"
    except FileNotFoundError:
        return False, "pm2 not found (install PM2)"
    except Exception as e:
        return False, str(e)[:200]


def get_updates(token: str, offset: int | None = None):
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=30"
    if offset is not None:
        url += f"&offset={offset}"
    with urllib.request.urlopen(url, timeout=35) as resp:
        return json.load(resp)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not allowed_chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return

    from telegram_notify import send_message
    send_message("🤖 Telegram Command bot running. /report /status /news [/news SPY] /start /stop /restart")

    offset = None
    while True:
        try:
            data = get_updates(token, offset=offset)
            if not data.get("ok"):
                time.sleep(5)
                continue
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id"))
                if chat_id != allowed_chat_id:
                    continue
                text = (msg.get("text") or "").strip()
                text_lower = text.lower()
                if text_lower in ("/report", "/status"):
                    send_message("⏳ Building report…")
                    try:
                        from status_report import run_status_report
                        tc, dc = _get_report_clients()
                        run_status_report(trading_client=tc, data_client=dc)
                    except Exception as e:
                        send_message(f"❌ Report failed: {e}")
                elif text_lower == "/start":
                    ok, msg_out = _run_pm2_start_bot()
                    send_message(f"✅ {msg_out}" if ok else f"❌ Start failed: {msg_out}")
                elif text_lower == "/stop":
                    ok, msg_out = _run_pm2_stop_bot()
                    send_message(f"✅ {msg_out}" if ok else f"❌ Stop failed: {msg_out}")
                elif text_lower == "/restart":
                    ok, msg_out = _run_pm2_restart_bot()
                    send_message(f"✅ {msg_out}" if ok else f"❌ Restart failed: {msg_out}")
                elif text_lower == "/news" or text_lower.startswith("/news "):
                    parts = text.split(maxsplit=1)
                    symbol = (parts[1].strip().upper() if len(parts) > 1 else "SPY") or "SPY"
                    send_message(f"⏳ News for {symbol}…")
                    try:
                        from agent.tavily_client import search_market_news_with_usage
                        results, usage = search_market_news_with_usage(symbol)
                        if not results:
                            send_message(f"📰 No news found for {symbol}.")
                        else:
                            lines = [f"📰 News for {symbol}:"]
                            for r in results[:8]:
                                title = (r.get("title") or "")[:80]
                                url = r.get("url") or ""
                                if url:
                                    lines.append(f"• {title}\n  {url}")
                                else:
                                    lines.append(f"• {title}")
                            cred = usage.get("credits")
                            if cred is not None:
                                lines.append(f"\n📊 API: Tavily {cred} cr")
                            msg = "\n".join(lines)
                            if len(msg) > 4000:
                                msg = msg[:3997] + "..."
                            send_message(msg)
                    except Exception as e:
                        send_message(f"❌ News failed: {e}")
        except Exception as e:
            print("Poll error:", e)
            time.sleep(10)


if __name__ == "__main__":
    main()

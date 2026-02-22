#!/usr/bin/env python3
"""
Long-poll Telegram for commands. When you send /report or /status to your bot,
replies with current status + SMA charts.
Run in background or PM2: python3 telegram_commands.py
Only the chat_id in .env can trigger commands.
"""
import json
import os
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
    send_message("🤖 Command bot running. Send /report or /status for a status report.")

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
                text = (msg.get("text") or "").strip().lower()
                if text in ("/report", "/status"):
                    send_message("⏳ Building report…")
                    try:
                        from status_report import run_status_report
                        run_status_report()
                    except Exception as e:
                        send_message(f"❌ Report failed: {e}")
        except Exception as e:
            print("Poll error:", e)
            time.sleep(10)


if __name__ == "__main__":
    main()

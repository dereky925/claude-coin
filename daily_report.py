#!/usr/bin/env python3
"""
Send a daily SMA chart report to Telegram for each BOT_SYMBOLS symbol.
Run once per day via cron, e.g.: 0 9 * * * cd /path && .venv/bin/python daily_report.py
"""
import os
import sys
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

from report_helpers import get_bars, build_sma_plot, build_combined_sma_plot


def main():
    symbols_raw = os.getenv("BOT_SYMBOLS", "SPY").strip()
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    fast = int(os.getenv("BOT_FAST_SMA", "10"))
    slow = int(os.getenv("BOT_SLOW_SMA", "30"))

    from telegram_notify import _is_configured, send_message, send_photo
    if not _is_configured():
        print("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        sys.exit(1)

    from alpaca_client import get_data_client
    data_client = get_data_client()

    send_message(f"📈 Daily SMA report — {', '.join(symbols)}")

    if len(symbols) > 1:
        path = build_combined_sma_plot(data_client, symbols, fast, slow)
        if path:
            try:
                send_photo(path)
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass
    else:
        for symbol in symbols:
            closes = get_bars(data_client, symbol, slow)
            path = build_sma_plot(closes, symbol, fast, slow)
            if path:
                try:
                    send_photo(path)
                finally:
                    try:
                        os.unlink(path)
                    except Exception:
                        pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Send current status (account, positions, signals) and SMA charts to Telegram.
Run manually: python3 status_report.py
"""
import gc
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

from report_helpers import (
    get_bars,
    build_sma_plot,
    build_combined_sma_plot,
    get_account_status,
    get_signals_text,
)


def run_status_report(
    trading_client=None,
    data_client=None,
):
    """Fetch account, positions, signals and SMA charts; send all to Telegram.
    Pass trading_client and/or data_client to reuse existing clients (e.g. from telegram_commands).
    """
    symbols_raw = os.getenv("BOT_SYMBOLS", "SPY").strip()
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    fast = int(os.getenv("BOT_FAST_SMA", "10"))
    slow = int(os.getenv("BOT_SLOW_SMA", "30"))

    from alpaca_client import get_data_client, get_trading_client
    paper_raw = os.getenv("BOT_PAPER", os.getenv("APCA_PAPER", "true")).lower()
    paper = paper_raw in ("true", "1", "yes")
    if trading_client is None:
        trading_client = get_trading_client(paper=paper)
    if data_client is None:
        data_client = get_data_client()

    from telegram_notify import send_message, send_photo

    status = get_account_status(trading_client)
    signals = get_signals_text(data_client, symbols, fast, slow)
    msg = "📊 Status Report 📈\n\n" + status + "\n\n" + signals
    send_message(msg)

    # One combined image when multiple symbols; otherwise one image per symbol
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

    # Clear matplotlib state and encourage GC to reclaim report allocations
    try:
        import matplotlib.pyplot as plt
        plt.close("all")
    except Exception:
        pass
    gc.collect()


def main():
    from telegram_notify import _is_configured
    if not _is_configured():
        print("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        sys.exit(1)
    run_status_report()


if __name__ == "__main__":
    main()

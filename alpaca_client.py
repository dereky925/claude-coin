"""
Shared Alpaca API clients. Loads credentials from .env.
Used by trading.py (manual orders) and bot.py (scheduled bot).
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    _env_dir = Path(__file__).resolve().parent
    _env_file = _env_dir / ".env"
    if _env_file.is_file():
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\r")
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip().strip("\r")
                    if key and os.environ.get(key) in (None, ""):
                        os.environ[key] = value


def _credentials():
    api_key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    if not api_key or not secret:
        raise RuntimeError(
            "Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY. Copy .env.example to .env and add your keys."
        )
    return api_key, secret


def get_trading_client(paper: bool | None = None):
    """TradingClient for orders and positions. paper=True uses paper API."""
    from alpaca.trading.client import TradingClient

    api_key, secret = _credentials()
    if paper is None:
        raw = os.getenv("APCA_PAPER", "true").lower()
        paper = raw in ("true", "1", "yes")
    return TradingClient(api_key=api_key, secret_key=secret, paper=paper)


def get_data_client():
    """StockHistoricalDataClient for bars. Uses same API keys (no paper/live distinction for data)."""
    from alpaca.data.historical import StockHistoricalDataClient

    api_key, secret = _credentials()
    return StockHistoricalDataClient(api_key=api_key, secret_key=secret)


def is_paper() -> bool:
    raw = os.getenv("APCA_PAPER", "true").lower()
    return raw in ("true", "1", "yes")

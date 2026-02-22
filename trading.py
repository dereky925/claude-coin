#!/usr/bin/env python3
"""
Alpaca trading connection check and optional paper order.
Loads credentials from .env. Run with --order SYMBOL to place one share market buy (paper).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent / ".env")

def get_client():
    api_key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    paper_raw = os.getenv("APCA_PAPER", "true").lower()
    paper = paper_raw in ("true", "1", "yes")

    if not api_key or not secret:
        print("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY. Copy .env.example to .env and add your keys.", file=sys.stderr)
        sys.exit(1)

    from alpaca.trading.client import TradingClient
    return TradingClient(api_key=api_key, secret_key=secret, paper=paper), paper


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Alpaca connection check and optional paper order")
    parser.add_argument("--order", metavar="SYMBOL", help="Place a 1-share market BUY order (paper) for SYMBOL")
    args = parser.parse_args()

    client, paper = get_client()
    mode = "paper" if paper else "live"
    print(f"Using Alpaca {mode} trading.")

    # Connection check: get account
    account = client.get_account()
    print(f"Account status: {account.status}")
    print(f"Buying power:  {account.buying_power}")
    print(f"Equity:        {account.equity}")

    if args.order:
        symbol = args.order.strip().upper()
        if not symbol:
            print("Provide a symbol, e.g. --order AAPL", file=sys.stderr)
            sys.exit(1)
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(order_data=order_data)
        print(f"Order submitted: {order.id} ({order.side} {order.qty} {order.symbol})")
    else:
        print("Run with --order SYMBOL to place a 1-share market BUY (e.g. --order AAPL).")


if __name__ == "__main__":
    main()

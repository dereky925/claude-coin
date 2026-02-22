#!/usr/bin/env python3
"""
Alpaca trading connection check and optional paper order.
Loads credentials from .env. Run with --order SYMBOL to place one share market buy (paper).
"""
import sys

from alpaca_client import get_trading_client, is_paper


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Alpaca connection check and optional paper order")
    parser.add_argument("--order", metavar="SYMBOL", help="Place a 1-share market BUY order (paper) for SYMBOL")
    args = parser.parse_args()

    client = get_trading_client()
    paper = is_paper()
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

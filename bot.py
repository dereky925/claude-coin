#!/usr/bin/env python3
"""
Scheduled momentum bot: fetches bars from Alpaca, runs SMA crossover, places orders.
Uses same strategy as backtest (strategies.momentum). Paper by default.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
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

# US regular session: 13:30-20:00 UTC (9:30 AM - 4 PM Eastern)
def _is_market_open() -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    hour, minute = now.hour, now.minute
    utc_min = hour * 60 + minute
    open_min = 13 * 60 + 30   # 13:30 UTC
    close_min = 20 * 60 + 0   # 20:00 UTC
    return open_min <= utc_min < close_min


def _config():
    symbols_raw = os.getenv("BOT_SYMBOLS", "SPY").strip()
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    fast = int(os.getenv("BOT_FAST_SMA", "10"))
    slow = int(os.getenv("BOT_SLOW_SMA", "30"))
    interval_min = int(os.getenv("BOT_INTERVAL_MINUTES", "15"))
    position_size = int(os.getenv("BOT_POSITION_SIZE", "1"))
    pd_raw = os.getenv("BOT_POSITION_DOLLARS", "").strip()
    position_dollars = int(pd_raw) if pd_raw.isdigit() else None
    paper_raw = os.getenv("BOT_PAPER", os.getenv("APCA_PAPER", "true")).lower()
    paper = paper_raw in ("true", "1", "yes")
    agent_raw = os.getenv("BOT_USE_AGENT", "false").lower()
    use_agent = agent_raw in ("true", "1", "yes")
    skip_same_bar_raw = os.getenv("BOT_SKIP_SAME_BAR", "true").lower()
    skip_same_bar = skip_same_bar_raw in ("true", "1", "yes")
    news_mode = (os.getenv("BOT_NEWS_MODE", "per_symbol") or "per_symbol").strip().lower()
    if news_mode not in ("per_symbol", "general", "hybrid"):
        news_mode = "per_symbol"
    return {
        "symbols": symbols,
        "fast_period": fast,
        "slow_period": slow,
        "interval_minutes": max(1, interval_min),
        "position_size": max(1, position_size),
        "position_dollars": position_dollars,
        "paper": paper,
        "use_agent": use_agent,
        "skip_same_bar": skip_same_bar,
        "news_mode": news_mode,
    }


def _state_dir() -> Path:
    return Path(__file__).resolve().parent / "state"


def _last_bar_path(symbol: str) -> Path:
    return _state_dir() / f"last_bar_{symbol}.json"


def _read_last_bar(symbol: str) -> dict:
    """Return {"date": "YYYY-MM-DD", "signal": "buy"|"sell"} or {}."""
    try:
        p = _last_bar_path(symbol)
        if not p.is_file():
            return {}
        import json
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_last_bar(symbol: str, bar_date: str, signal: str) -> None:
    try:
        _state_dir().mkdir(parents=True, exist_ok=True)
        import json
        with open(_last_bar_path(symbol), "w", encoding="utf-8") as f:
            json.dump({"date": bar_date, "signal": signal}, f)
    except Exception:
        pass


def _get_bars(data_client, symbol: str, slow_period: int):
    """Daily bars for symbol, enough for slow SMA (plus buffer). Uses IEX feed (free tier)."""
    import pandas as pd
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=slow_period + 60)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,  # free tier; SIP requires paid subscription
    )
    bars = data_client.get_stock_bars(req)
    if not bars or symbol not in bars.data or not bars.data[symbol]:
        return None
    # Build close series from Bar objects (bars.data[symbol] is list of Bar)
    close_series = pd.Series(
        {b.timestamp: b.close for b in bars.data[symbol]},
        dtype=float,
    ).sort_index()
    return close_series


def _get_position_qty(trading_client, symbol: str) -> float:
    """Current position qty for symbol, or 0."""
    try:
        pos = trading_client.get_open_position(symbol)
        return float(pos.qty)
    except Exception:
        return 0.0


def _get_position(trading_client, symbol: str):
    """Open position for symbol, or None."""
    try:
        return trading_client.get_open_position(symbol)
    except Exception:
        return None


def _account_summary(trading_client) -> str:
    """Build a short account status string (equity, cash, daily change, positions)."""
    try:
        account = trading_client.get_account()
        equity = float(account.equity or 0)
        cash = float(account.cash or 0)
        last_equity = float(account.last_equity or 0)
        daily_change = equity - last_equity if last_equity else 0
        daily_str = f"{daily_change:+.2f}" if last_equity else "—"
        lines = [
            f"Equity: ${equity:,.2f}",
            f"Cash:   ${cash:,.2f}",
            f"Today:  ${daily_str}",
        ]
        try:
            positions = trading_client.get_all_positions()
        except Exception:
            positions = []
        if positions:
            lines.append("")
            for pos in positions:
                qty = float(pos.qty or 0)
                upl = float(pos.unrealized_pl or 0)
                sym = getattr(pos, "symbol", None) or getattr(pos, "symbol_id", "?")
                lines.append(f"  {sym}: {qty:.0f} sh  P&L ${upl:+,.2f}")
        return "\n".join(lines)
    except Exception:
        return "Could not load account."


def run_once(cfg: dict, trading_client, data_client, log):
    """Fetch bars, compute signals, place orders for each symbol."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    from strategies.momentum import signal_at_end

    if not _is_market_open():
        log.debug("Market closed, skipping run_once")
        return

    use_agent = cfg.get("use_agent", False)
    skip_same_bar = cfg.get("skip_same_bar", True)
    news_mode = cfg.get("news_mode", "per_symbol")
    general_results, general_usage = [], {}
    general_fetched = False

    for symbol in cfg["symbols"]:
        closes = _get_bars(data_client, symbol, cfg["slow_period"])
        if closes is None or len(closes) < cfg["slow_period"]:
            log.warning("%s: not enough bars, skip", symbol)
            continue

        signal = signal_at_end(
            closes,
            fast_period=cfg["fast_period"],
            slow_period=cfg["slow_period"],
        )
        qty = _get_position_qty(trading_client, symbol)
        latest_close = float(closes.iloc[-1]) if not closes.empty else 0.0
        last_ts = closes.index[-1]
        bar_date = str(last_ts.date()) if hasattr(last_ts, "date") else str(last_ts)[:10]

        if signal == "buy" and qty == 0:
            if skip_same_bar:
                last = _read_last_bar(symbol)
                if last.get("date") == bar_date and last.get("signal") == "buy":
                    log.info("%s BUY skipped (already acted on bar %s)", symbol, bar_date)
                    continue
            buy_qty = max(1, int(cfg["position_dollars"] / latest_close)) if cfg.get("position_dollars") else cfg["position_size"]
            adv = None
            if use_agent:
                try:
                    if news_mode == "hybrid" and not general_fetched:
                        try:
                            from agent.tavily_client import search_market_news_general
                            general_results, general_usage = search_market_news_general()
                            general_fetched = True
                        except Exception as e:
                            log.warning("General news fetch failed: %s", e)
                    from agent.agent import get_agent_action
                    adv = get_agent_action(
                        symbol, "buy", latest_close, 0.0, use_agent=True,
                        general_snippets_override=general_results if news_mode == "hybrid" else None,
                    )
                    action, reason = adv.get("action", "confirm"), adv.get("reason", "")
                    log.info("%s agent action=%s reason=%s", symbol, action, reason[:80] if reason else "")
                    if action == "skip" or action == "override_sell":
                        log.info("%s BUY skipped by agent", symbol)
                        continue
                    if action == "reduce":
                        buy_qty = max(1, buy_qty // 2)
                except Exception as e:
                    log.warning("%s agent error, skip trade: %s", symbol, e)
                    continue
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=buy_qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            order = trading_client.submit_order(order_data=order_data)
            if skip_same_bar:
                _write_last_bar(symbol, bar_date, "buy")
            log.info("%s BUY qty=%s order_id=%s", symbol, buy_qty, order.id)
            try:
                from telegram_notify import notify_trade
                summary = _account_summary(trading_client)
                api_usage = {}
                if adv:
                    u = adv.get("usage") or {}
                    api_usage["gemini"] = u.get("gemini")
                    tc = (general_usage.get("credits") or 0) + (u.get("tavily") or {}).get("credits", 0)
                    if tc:
                        api_usage["tavily"] = {"credits": tc}
                notify_trade(
                    symbol, "buy", buy_qty, order.id, cfg["paper"],
                    account_summary=summary,
                    agent_reason=adv.get("reason") if adv else None,
                    news_links=adv.get("news") if adv else None,
                    api_usage=api_usage if api_usage else None,
                )
            except Exception:
                pass
        elif signal == "sell" and qty > 0:
            if skip_same_bar:
                last = _read_last_bar(symbol)
                if last.get("date") == bar_date and last.get("signal") == "sell":
                    log.info("%s SELL skipped (already acted on bar %s)", symbol, bar_date)
                    continue
            sell_qty = int(qty) if qty >= 1 else 1
            adv = None
            if use_agent:
                try:
                    if news_mode == "hybrid" and not general_fetched:
                        try:
                            from agent.tavily_client import search_market_news_general
                            general_results, general_usage = search_market_news_general()
                            general_fetched = True
                        except Exception as e:
                            log.warning("General news fetch failed: %s", e)
                    from agent.agent import get_agent_action
                    adv = get_agent_action(
                        symbol, "sell", latest_close, qty, use_agent=True,
                        general_snippets_override=general_results if news_mode == "hybrid" else None,
                    )
                    action, reason = adv.get("action", "confirm"), adv.get("reason", "")
                    log.info("%s agent action=%s reason=%s", symbol, action, reason[:80] if reason else "")
                    if action == "skip":
                        log.info("%s SELL skipped by agent", symbol)
                        continue
                    if action == "reduce":
                        sell_qty = max(1, sell_qty // 2)
                except Exception as e:
                    log.warning("%s agent error, skip trade: %s", symbol, e)
                    continue
            pos = _get_position(trading_client, symbol)
            pnl_dollars = None
            if pos and float(pos.qty or 0) != 0:
                upl = float(pos.unrealized_pl or 0)
                pos_qty = float(pos.qty)
                pnl_dollars = (upl / pos_qty) * sell_qty if pos_qty else None
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=sell_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = trading_client.submit_order(order_data=order_data)
            if skip_same_bar:
                _write_last_bar(symbol, bar_date, "sell")
            log.info("%s SELL qty=%s order_id=%s", symbol, sell_qty, order.id)
            try:
                from telegram_notify import notify_trade
                summary = _account_summary(trading_client)
                api_usage = {}
                if adv:
                    u = adv.get("usage") or {}
                    api_usage["gemini"] = u.get("gemini")
                    tc = (general_usage.get("credits") or 0) + (u.get("tavily") or {}).get("credits", 0)
                    if tc:
                        api_usage["tavily"] = {"credits": tc}
                notify_trade(
                    symbol, "sell", sell_qty, order.id, cfg["paper"],
                    pnl_dollars=pnl_dollars, account_summary=summary,
                    agent_reason=adv.get("reason") if adv else None,
                    news_links=adv.get("news") if adv else None,
                    api_usage=api_usage if api_usage else None,
                )
            except Exception:
                pass
        else:
            log.info("%s %s (position=%s) — no trade", symbol, signal, qty)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Momentum bot: SMA crossover, scheduled or once")
    parser.add_argument("--once", action="store_true", help="Run once and exit (e.g. for cron)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger(__name__)

    # Send "starting" to Telegram first (before Alpaca), so we know the process and Telegram work
    try:
        from telegram_notify import _is_configured, send_message
        if _is_configured():
            send_message("🪙 Claude Coin Bot Starting… 🤖💤")
            log.info("Telegram startup message sent")
        else:
            log.info("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
    except Exception as e:
        log.warning("Telegram startup: %s", e)

    from alpaca_client import get_data_client, get_trading_client

    cfg = _config()
    trading_client = get_trading_client(paper=cfg["paper"])
    data_client = get_data_client()

    mode = "paper" if cfg["paper"] else "live"
    log.info("Bot started %s | symbols=%s | fast=%s slow=%s | interval=%s min", mode, cfg["symbols"], cfg["fast_period"], cfg["slow_period"], cfg["interval_minutes"])

    try:
        from telegram_notify import _is_configured, notify_account_status, send_message
        if _is_configured():
            symbols_line = ", ".join(cfg["symbols"])
            send_message(
                f"🪙 Claude Coin bot started\n\n"
                f"Mode: {mode}\n"
                f"Tickers: {symbols_line}\n"
                f"Interval: {cfg['interval_minutes']} min"
            )
            try:
                notify_account_status(_account_summary(trading_client))
            except Exception:
                pass
    except Exception as e:
        log.warning("Telegram started/account: %s", e)

    if args.once:
        run_once(cfg, trading_client, data_client, log)
        return

    while True:
        try:
            run_once(cfg, trading_client, data_client, log)
        except Exception as e:
            log.exception("Run failed: %s", e)
            try:
                from telegram_notify import notify_error
                notify_error(str(e))
            except Exception:
                pass
        time.sleep(cfg["interval_minutes"] * 60)


if __name__ == "__main__":
    main()

# Claude Coin

A trading bot that runs a **momentum (SMA crossover)** strategy on Alpaca, with an optional **agentic layer** (Gemini + Tavily) that advises on each trade using market news. Supports paper and live trading, Telegram alerts, and remote control via Telegram commands.

---

## How the trading algorithm works

### Core: SMA crossover (momentum)

The bot uses a **simple moving average (SMA) crossover** on **daily** bars:

- **Fast SMA** — average of the last N days’ closing prices (default 10). Reacts quickly to recent moves.
- **Slow SMA** — average of the last M days (default 30). Slower, smoother trend line.

Logic:

- **Buy** when Fast SMA **crosses above** Slow SMA and you have **no position** in that symbol.
- **Sell** when Fast SMA **crosses below** Slow SMA and you **hold a position**.
- **Hold** when the two are on the same side (no crossover) or you’re flat and the signal says hold.

So trades occur only on crossovers; between crossovers the bot does nothing for that symbol. The same logic is used in **backtests** (`strategies.momentum`) and in the **live bot** so behavior is consistent.

### Data and execution

- **Data:** Daily bars come from **Alpaca** (IEX feed, free tier). The bot requests enough history to compute the slow SMA (plus buffer).
- **Execution:** One “cycle” runs every **`BOT_INTERVAL_MINUTES`** (default 15): for each symbol it fetches bars → computes `signal_at_end()` (buy/sell/hold) → if buy/sell and position allows, may place a **market order** (size from `BOT_POSITION_SIZE` or `BOT_POSITION_DOLLARS`).
- **Market hours:** The bot **does not trade when the market is closed**. It skips the whole cycle on weekends (Sat/Sun) and outside US regular session (13:30–20:00 UTC). No orders and no bar fetches during that time.
- **Same-bar dedup:** With **`BOT_SKIP_SAME_BAR=true`** (default), the bot stores the last bar date and signal per symbol in `state/`. If you restart and the latest bar still has the same buy (or sell) signal, it **does not** place the same order again for that bar, avoiding duplicate buys on restart.

### Optional agentic layer (Gemini + Tavily)

If **`BOT_USE_AGENT=true`**, the bot does **not** rely only on the SMA. Before placing a buy or sell it:

1. **News (Tavily):** Fetches recent market/symbol news (only for symbols that actually have a buy or sell signal this run). Mode is set by **`BOT_NEWS_MODE`**:
   - **per_symbol** (default) — one Tavily search per symbol with a signal (query like “{symbol} stock news market”).
   - **hybrid** — one **general** market search (e.g. “US stock market S&P 500 news”) the first time any symbol has a signal in that run, plus **per-symbol** search for each symbol with a signal. The agent sees both broad market and ticker-specific context.
2. **Advisory (Gemini):** Sends the technical signal (buy/sell), last close, position size, and news snippets to **Gemini**. The model replies with one of:
   - **confirm** — proceed with full size.
   - **reduce** — proceed with half size.
   - **skip** — do not trade this bar.
   - **override_sell** — for a buy signal, do not buy (or can imply sell if long).

The **SMA remains the primary signal**; the agent only adjusts whether and how much to trade. On API or parse errors the bot defaults to **skip** (no trade). Trade notifications can include the agent’s reason, news links, and API usage (Gemini tokens, Tavily credits).

---

## Project Structure

### Main scripts (entry points)

| Script | Purpose |
|--------|--------|
| **`bot.py`** | **Main trading loop.** Run this for the live/paper bot. Loads config from `.env`, connects to Alpaca via `alpaca_client`, and every `BOT_INTERVAL_MINUTES` runs one cycle: market-hours check → for each symbol fetch bars → SMA signal → optional agent → place orders → Telegram notify. Uses `strategies.momentum.signal_at_end` and optionally `agent.agent.get_agent_action`. |
| **`telegram_commands.py`** | **Telegram command listener.** Long-polls Telegram; when you send `/status`, `/news`, `/start`, `/stop`, `/restart` from the allowed chat it runs the right handler (status report, news fetch, or PM2 start/stop/restart for the trading bot). Uses `alpaca_client` and `status_report` for `/status`, and `agent.tavily_client` for `/news`. |
| **`backtest.py`** | **Backtest the same SMA strategy** on historical daily data (Yahoo Finance). No Alpaca keys needed. Uses `strategies.momentum.signals` (full series). |
| **`trading.py`** | **One-off Alpaca check and optional single order.** Prints account info; with `--order SYMBOL` places one market buy (paper by default). Uses `alpaca_client` only. |
| **`status_report.py`** | **Build and send status + SMA charts to Telegram.** Used by `/status` (via `telegram_commands`) or run manually. Uses `report_helpers`, `alpaca_client`, `telegram_notify`. |
| **`daily_report.py`** | **Daily SMA chart report.** Intended for cron (e.g. once per day). Sends charts to Telegram. |
| **`test_agent_layer.py`** | **Test Tavily and Gemini.** Verifies API keys and that the agent returns a valid action; run with `--verbose` for raw Tavily response shape. |

### Shared and support modules

| File | Purpose |
|------|--------|
| **`alpaca_client.py`** | **Alpaca API clients.** Loads `.env`; exposes `get_trading_client(paper=...)` and `get_data_client()` for orders and historical bars. Used by `bot.py`, `trading.py`, `telegram_commands.py`, `status_report.py`. |
| **`telegram_notify.py`** | **Send messages and trade alerts to Telegram.** `send_message()`, `notify_trade()`, `notify_account_status()`, `notify_error()`. Used by the bot (startup, trades, errors) and by status/daily reports and command replies. |
| **`strategies/momentum.py`** | **SMA crossover logic.** `sma()`, `signals()` (full series for backtest), `signal_at_end()` (single buy/sell/hold for live bot). Used by `bot.py`, `backtest.py`, and report helpers. |
| **`report_helpers.py`** | **Bars, SMA plots, account text, signals text.** Used by `status_report.py` and `daily_report.py` to build the content sent to Telegram. |

### Agentic layer (`agent/`)

| File | Purpose |
|------|--------|
| **`agent/agent.py`** | **Orchestrator.** `get_agent_action(symbol, signal, last_close, position_qty, ...)` — fetches news (or uses overrides for hybrid), calls Gemini, returns `{action, reason, news, usage}`. Used by `bot.py` when `BOT_USE_AGENT=true`. |
| **`agent/tavily_client.py`** | **Tavily search.** `search_market_news(symbol)` (returns list of `{title, url, snippet}`), `search_market_news_with_usage(symbol)` (returns list + credits), `search_market_news_general()` for hybrid. Used by `agent/agent.py`, `bot.py` (hybrid), `telegram_commands.py` (/news). |
| **`agent/gemini_client.py`** | **Gemini advisory.** Takes symbol, technical signal, last close, position, news snippets; calls Gemini; parses ACTION/REASON and returns `{action, reason, usage}` (with token counts and estimated cost). Used only via `agent/agent.py`. |

### Config and state

- **`.env`** — Secrets and tuning (see `.env.example`). Loaded by `alpaca_client`, `bot`, `telegram_commands`, `telegram_notify`, and the agent modules. Never commit `.env`.
- **`state/`** — Per-symbol “last bar” state for same-bar skip (created by `bot.py`). Gitignored.
- **`ecosystem.config.cjs`** — PM2 config: defines `claude-coin-bot` (bot.py) and `telegram-commands` (telegram_commands.py).

### Call flow summary

- **Trading cycle:** `bot.py` → `alpaca_client` (data + trading) → `strategies.momentum.signal_at_end` → [if agent] `agent.agent.get_agent_action` → `agent.tavily_client` (+ optional `search_market_news_general`) and `agent.gemini_client` → Alpaca order → `telegram_notify.notify_trade`.
- **Telegram /status:** `telegram_commands.py` → `status_report.run_status_report` → `report_helpers` + `alpaca_client` + `telegram_notify`.
- **Telegram /news:** `telegram_commands.py` → `agent.tavily_client.search_market_news_with_usage` → `telegram_notify.send_message`.

---

## Prerequisites

- Python 3.8+
- [Alpaca account](https://alpaca.markets) (paper trading is free)
- For the agentic layer: [Google AI (Gemini)](https://ai.google.dev) API key and [Tavily](https://tavily.com) API key
- For Telegram: bot token and chat ID from Telegram

---

## Setup

### 1. Alpaca API keys

In the [Alpaca dashboard](https://app.alpaca.markets): **Paper Trading** → **API Keys** → **Generate New Keys**. Save the Key ID and Secret (the secret is shown only once).

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Or with a venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`. Minimum for the bot:

- `APCA_API_KEY_ID` — Alpaca key ID  
- `APCA_API_SECRET_KEY` — Alpaca secret  
- `APCA_PAPER=true` for paper, or `false` for live  

Optional but recommended:

- `BOT_SYMBOLS` — e.g. `SPY,AAPL,QQQ`  
- `BOT_POSITION_DOLLARS` — e.g. `5000` for ~$5k per buy  
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for alerts and commands  
- `BOT_USE_AGENT=true`, `GEMINI_API_KEY`, `TAVILY_API_KEY` for the agentic layer  

See `.env.example` for all options. Never commit `.env` (it’s in `.gitignore`).

---

## Parameters you can tune

All optional; defaults are in the table.

| Variable | Default | What it does |
|----------|---------|--------------|
| `BOT_SYMBOLS` | `SPY` | Comma-separated tickers to trade. |
| `BOT_FAST_SMA` | `10` | Fast SMA length (days). |
| `BOT_SLOW_SMA` | `30` | Slow SMA length (days). |
| `BOT_INTERVAL_MINUTES` | `15` | Minutes between each cycle. |
| `BOT_POSITION_SIZE` | `1` | Shares per buy (use this or `BOT_POSITION_DOLLARS`). |
| `BOT_POSITION_DOLLARS` | — | Target $ per buy; bot converts to shares. Overrides `BOT_POSITION_SIZE` if set. |
| `BOT_PAPER` | follows `APCA_PAPER` | `true` = paper, `false` = live. |
| `BOT_USE_AGENT` | `false` | `true` = use Gemini + Tavily advisory on each potential trade. |
| `BOT_SKIP_SAME_BAR` | `true` | Avoid duplicate order for the same bar after restart (uses `state/`). |
| `BOT_NEWS_MODE` | `per_symbol` | `per_symbol` \| `general` \| `hybrid` for how news is fetched when agent is on. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model for the agent (e.g. `gemini-2.5-pro` for deeper reasoning). |

After changing `.env`, restart the bot for changes to take effect.

### Position sizing and risk

For a ~$100k account, 2–5% per position ($2k–$5k per symbol) is a common range; 5–10% is more aggressive. Use `BOT_POSITION_DOLLARS` (e.g. `5000`) for consistent dollar sizing. No setting guarantees profit; this is about risk and diversification.

---

## How to run the bot

### Foreground (testing)

```bash
python3 bot.py
```

Runs until you stop it (Ctrl+C). Use `python3 bot.py --once` for a single cycle (e.g. for cron).

### Background with PM2 (recommended)

```bash
cd "/root/Claude Coin"   # or your project path
pm2 start ecosystem.config.cjs
pm2 save
```

This starts both **claude-coin-bot** (trading) and **telegram-commands** (Telegram listener). To have PM2 start on server boot:

```bash
pm2 startup
# run the command it prints, then:
pm2 save
```

### PM2 commands

| What you want | Command |
|---------------|--------|
| See if apps are running | `pm2 status` |
| Live logs (trading bot) | `pm2 logs claude-coin-bot` |
| Live logs (Telegram commands) | `pm2 logs telegram-commands` |
| Restart trading bot | `pm2 restart claude-coin-bot` |
| Stop trading bot | `pm2 stop claude-coin-bot` |
| Start trading bot again | `pm2 start claude-coin-bot` |
| Stop everything | `pm2 stop all` |
| Clear logs | `pm2 flush claude-coin-bot` |

After editing code or `.env`, restart the bot so it picks up changes.

---

## Telegram

### Alerts

With `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set, the bot sends Telegram messages when it **starts**, when it **places a trade** (including optional agent reason, news links, and API usage), and when it hits an **error**. It does not message on every cycle.

**Setup:** Create a bot with [@BotFather](https://t.me/BotFather), add the token and chat ID to `.env`. Get your chat ID by messaging the bot and running `python3 telegram_get_chat_id.py` (or use a service like @userinfobot). Test with:

```bash
python3 telegram_notify.py
```

### Telegram commands (telegram_commands.py)

Run the command listener so the bot responds in Telegram (e.g. under PM2 as **telegram-commands**). Only the chat ID in `.env` can trigger commands.

| Command | What it does |
|---------|----------------|
| **/status** | Sends current account, positions, signals, and SMA charts. |
| **/news** | Market news for default symbol (SPY). |
| **/news SYMBOL** | News for a specific ticker. |
| **/start** | Starts the **trading bot** only (`pm2 start claude-coin-bot` + save). |
| **/stop** | Stops the trading bot (`pm2 stop claude-coin-bot`). |
| **/restart** | Restarts the trading bot (`pm2 restart claude-coin-bot`). |

Startup and stop/restart affect only the trading bot, not the Telegram command process. To start the full stack (e.g. after a reboot), run `pm2 start ecosystem.config.cjs` and `pm2 save` from the shell.

### Status report without Telegram commands

To send status + charts once without the command listener:

```bash
python3 status_report.py
```

### Daily report (cron)

Example: daily SMA chart at 9:00 AM:

```bash
0 9 * * * cd "/root/Claude Coin" && /root/Claude\ Coin/.venv/bin/python daily_report.py
```

---

## Other commands

### Alpaca connection and one test order

```bash
python3 trading.py
```

Shows account status. To place a single 1-share market buy (paper):

```bash
python3 trading.py --order AAPL
```

### Backtest (no API keys)

Uses Yahoo Finance:

```bash
python3 backtest.py SPY
python3 backtest.py AAPL --fast 10 --slow 30 --start 2022-01-01 --csv equity.csv
```

Options: `--fast`, `--slow`, `--start`, `--end`, `--capital`, `--csv FILE`.

### Test agentic layer

```bash
python3 test_agent_layer.py
```

Checks Tavily and Gemini and runs one full agent call. Use `--verbose` to inspect Tavily response shape.

---

## Safety

- Keep `.env` out of version control; it contains secrets.
- Defaults are **paper** trading. Set `APCA_PAPER=false` or `BOT_PAPER=false` only when you intend to use real money.
- Backtest and past results do not guarantee future performance.
- The agent can only advise (confirm/reduce/skip/override); it cannot place orders by itself. On agent or API errors the bot defaults to skipping the trade.

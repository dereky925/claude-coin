# Claude Coin

A small Alpaca trading bot that runs a **momentum (SMA crossover)** strategy. Use it for paper trading or live, with optional Telegram alerts.

---

## Prerequisites

- Python 3.8+
- [Alpaca account](https://alpaca.markets) (paper trading is free)

---

## Setup

### 1. Get Alpaca API keys

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

Edit `.env` and set at least:

- `APCA_API_KEY_ID` — your Alpaca API key ID  
- `APCA_API_SECRET_KEY` — your Alpaca secret key  
- `APCA_PAPER=true` for paper trading, or `false` for live

Never commit `.env` (it’s in `.gitignore`).

---

## What the bot does

### Which stocks it watches

Controlled by **`BOT_SYMBOLS`** in `.env`. Default is **SPY** (S&P 500 ETF). You can use several symbols separated by commas, e.g. `SPY,AAPL,QQQ`.

### Strategy: SMA crossover

- **SMA** = Simple Moving Average (average of the last N days’ closing prices).
- The bot uses two daily SMAs:
  - **Fast SMA** (default 10 days) — reacts quickly to recent price moves.
  - **Slow SMA** (default 30 days) — slower, smoother line.
- Each cycle it looks at the **latest daily close** and compares the two averages:
  - **Buy** when Fast SMA is **above** Slow SMA and you have **no position** in that symbol.
  - **Sell** when Fast SMA is **below** Slow SMA and you **have a position**.
  - Otherwise it does nothing (hold).

So trades only happen when the fast line crosses above or below the slow line. That might be every few days or less, depending on the symbol and market.

### How often it runs

The bot runs one “check” (fetch data → compute signal → maybe place one order), then sleeps. The sleep length is **`BOT_INTERVAL_MINUTES`** (default **15**). So by default it runs **every 15 minutes**. It does **not** trade every time — only when the crossover rule says buy or sell and your position allows it.

---

## Parameters you can tune

All of these are optional in `.env`. If you don’t set them, the defaults below are used.

| Variable | Default | What it does |
|----------|---------|--------------|
| `BOT_SYMBOLS` | `SPY` | Comma-separated tickers to trade (e.g. `SPY,AAPL,QQQ`). |
| `BOT_FAST_SMA` | `10` | Length of the fast moving average (days). |
| `BOT_SLOW_SMA` | `30` | Length of the slow moving average (days). |
| `BOT_INTERVAL_MINUTES` | `15` | Minutes between each run (e.g. `30` = every 30 min). |
| `BOT_POSITION_SIZE` | `1` | Number of shares to buy per buy signal (use this **or** `BOT_POSITION_DOLLARS`). |
| `BOT_POSITION_DOLLARS` | — | Target dollar amount per buy; bot converts to shares (e.g. `5000`). If set, overrides `BOT_POSITION_SIZE`. |
| `BOT_PAPER` | follows `APCA_PAPER` | `true` = paper trading, `false` = live. |

After changing `.env`, restart the bot for changes to take effect.

### Position sizing and risk

For a **~$100k** account, a common approach is to risk or allocate **2–5% per position** ($2k–$5k per symbol) to limit concentration; **5–10%** ($5k–$10k) is more aggressive. Use **`BOT_POSITION_DOLLARS`** (e.g. `5000`) for consistent dollar sizing. No setting "maximizes profit" — larger size can mean larger gains or larger losses; this is about risk and diversification.

---

## How to run the bot

### Run in the foreground (for testing)

```bash
python3 bot.py
```

Runs in a loop until you stop it (Ctrl+C). Use `python3 bot.py --once` to run a single cycle and exit (e.g. for cron).

### Run in the background with PM2 (recommended)

So the bot keeps running and restarts after a reboot:

```bash
cd "/root/Claude Coin"   # or your project path
pm2 start ecosystem.config.cjs
pm2 save
```

To have PM2 start on server boot:

```bash
pm2 startup
# run the command it prints, then:
pm2 save
```

---

## Basic commands (PM2)

| What you want | Command |
|---------------|--------|
| See if the bot is running | `pm2 status` |
| View live logs | `pm2 logs claude-coin-bot` |
| Last 50 log lines | `pm2 logs claude-coin-bot --lines 50` |
| Restart the bot | `pm2 restart claude-coin-bot` |
| Stop the bot | `pm2 stop claude-coin-bot` |
| Start again after stop | `pm2 start claude-coin-bot` |
| Clear old logs | `pm2 flush claude-coin-bot` |

After editing code or `.env`, run `pm2 restart claude-coin-bot` so the bot picks up changes.

---

## Telegram alerts

The bot can send Telegram messages when it **starts**, when it **places a trade**, and when it hits an **error**. It does **not** message on every run — only those events.

### Setup

1. In Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot`, and follow the prompts. Copy the **token**.
2. In `.env` add:
   ```bash
   TELEGRAM_BOT_TOKEN=your_token_here
   ```
3. In Telegram, open your new bot and send it any message (e.g. `/start`). Then on your machine run:
   ```bash
   python3 telegram_get_chat_id.py
   ```
   (If that script is missing, you can get your chat ID from a service like @userinfobot after messaging your bot.)
4. Add the printed value to `.env`:
   ```bash
   TELEGRAM_CHAT_ID=123456789
   ```
5. Restart the bot. You should get a startup message and then alerts for trades and errors.

To test without running the full bot:

```bash
python3 telegram_notify.py
```

If you see the test message in Telegram, alerts are configured correctly.

---

## Status report and SMA charts

You can get the **current account, positions, signals, and SMA charts** in Telegram in two ways.

### 1. Trigger from Telegram (recommended)

Run the command listener so the bot responds to **/report** or **/status**:

```bash
python3 telegram_commands.py
```

Keep it running (e.g. in a separate terminal or add to PM2). Then in Telegram, send your bot **/report** or **/status** — it will reply with a status message and SMA chart(s) for each symbol.

### 2. Run manually on the server

```bash
python3 status_report.py
```

Sends the same status + charts to Telegram immediately. No need for the command bot to be running.

### Daily SMA report (cron)

To get a **daily chart report** (SMA plots only) at a fixed time, run `daily_report.py` once per day via cron. Example: 9:00 AM every day:

```bash
0 9 * * * cd "/root/Claude Coin" && /root/Claude\ Coin/.venv/bin/python daily_report.py
```

Adjust the path and time as needed. Uses the same `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as alerts.

---

## Other commands

### Check Alpaca connection and account

```bash
python3 trading.py
```

### Place a single 1-share market BUY (paper)

```bash
python3 trading.py --order AAPL
```

### Backtest the same strategy (no API keys)

Uses Yahoo Finance data:

```bash
python3 backtest.py SPY
python3 backtest.py AAPL --fast 10 --slow 30 --start 2022-01-01 --csv equity.csv
```

Options: `--fast`, `--slow`, `--start`, `--end`, `--capital`, `--csv FILE`.

---

## Safety

- Keep `.env` out of version control; it contains secrets.
- Defaults are **paper** trading. Set `APCA_PAPER=false` or `BOT_PAPER=false` only when you intend to use real money.
- Backtest and past results do not guarantee future performance.

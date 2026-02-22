# Claude Coin

Alpaca trading: manual orders, **backtested momentum strategy**, and an optional scheduled bot.

## Prerequisites

- Python 3.8+
- [Alpaca account](https://alpaca.markets) (paper trading is free)

## Setup

1. **Get API keys**  
   In the [Alpaca dashboard](https://app.alpaca.markets), open Paper Trading → API Keys → Generate New Keys. Save the Key ID and Secret (the secret is shown only once).

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials**  
   Copy the example env file and add your keys (never commit `.env`):
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set:
   - `APCA_API_KEY_ID` — your Alpaca API key ID  
   - `APCA_API_SECRET_KEY` — your Alpaca secret key  
   - `APCA_PAPER=true` for paper trading, or `false` for live

## Usage

### Manual trading (connection check and one-off orders)

**Check connection and print account info (paper by default):**
```bash
python trading.py
```

**Place a 1-share market BUY order (paper):**
```bash
python trading.py --order AAPL
```

### Backtest (no API keys required)

Backtest the SMA crossover strategy on historical data (uses Yahoo Finance):

```bash
python backtest.py SPY
python backtest.py AAPL --fast 10 --slow 30 --start 2022-01-01 --csv equity.csv
```

Options: `--fast`, `--slow`, `--start`, `--end`, `--capital`, `--csv FILE`.

### Momentum bot (scheduled)

Same strategy as the backtest; runs against Alpaca and can place paper (or live) orders. Optional env vars: `BOT_SYMBOLS`, `BOT_FAST_SMA`, `BOT_SLOW_SMA`, `BOT_INTERVAL_MINUTES`, `BOT_POSITION_SIZE`, `BOT_PAPER`. Defaults: SPY, 10/30 SMA, 15 min, 1 share, paper.

**Run once (e.g. from cron):**
```bash
python bot.py --once
```

**Run in a loop every N minutes:**
```bash
python bot.py
```

### Telegram alerts

The momentum bot can send you Telegram messages when it starts, when it places a trade, and when it hits an error.

1. **Create a bot** (if you haven’t): In Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot`, follow the prompts. Copy the **token** (e.g. `8414964143:AAG...`).

2. **Add the token to `.env`:**
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   ```
   (Use the token from BotFather; never commit it.)

3. **Get your Chat ID:** In Telegram, open your bot and send it any message (e.g. `/start`). Then run:
   ```bash
   python telegram_get_chat_id.py
   ```
   Copy the printed line into `.env`:
   ```bash
   TELEGRAM_CHAT_ID=123456789
   ```

4. **Restart the trading bot.** You’ll get a startup message and then alerts for each trade and any errors. If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing, the bot runs as before and simply skips Telegram.

## Safety

- `.env` is in `.gitignore`; keep your keys out of version control.
- Default is paper trading. Set `APCA_PAPER=false` or `BOT_PAPER=false` only when you intend to trade with real money.
- Backtest results do not guarantee future performance.

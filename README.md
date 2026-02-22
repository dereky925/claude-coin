# Claude Coin

Minimal Alpaca trading setup: connection check and optional paper order.

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

**Check connection and print account info (paper by default):**
```bash
python trading.py
```

**Place a 1-share market BUY order (paper):**
```bash
python trading.py --order AAPL
```

## Safety

- `.env` is in `.gitignore`; keep your keys out of version control.
- Default is paper trading. Set `APCA_PAPER=false` only when you intend to trade with real money.

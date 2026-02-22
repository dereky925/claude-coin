"""
Send messages to Telegram. Used by the trading bot for trade alerts and errors.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

def _load_env():
    """Load .env from script directory (handles paths with spaces and CRLF)."""
    script_dir = Path(__file__).resolve().parent
    try:
        from dotenv import load_dotenv
        load_dotenv(script_dir / ".env")
        load_dotenv(".env")
    except Exception:
        pass
    # Fallback: parse .env ourselves (dotenv can fail with path spaces / CRLF)
    for name in (".env", ".env.local"):
        path = script_dir / name
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip().strip("\r")
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key, value = key.strip().strip("\r"), value.strip().strip("\r")
                        if key and os.environ.get(key) in (None, ""):
                            os.environ[key] = value
        except Exception:
            pass


_load_env()


def _is_configured() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return bool(token and chat_id)


def send_message(text: str) -> bool:
    """
    Send a text message to the configured Telegram chat.
    Returns True if sent, False if not configured or on error.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


class _MultipartPhotoReader:
    """File-like that streams multipart/form-data for sendPhoto without loading the whole image into memory."""

    def __init__(self, file_path: str, chat_id: str, boundary: str = "----ClaudeCoinBoundary"):
        self._boundary = boundary.encode()
        self._prefix = (
            b"--" + self._boundary + b"\r\n"
            b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' + chat_id.encode() + b"\r\n"
            b"--" + self._boundary + b"\r\n"
            b'Content-Disposition: form-data; name="photo"; filename="chart.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
        )
        self._suffix = b"\r\n--" + self._boundary + b"--\r\n"
        self._file = open(file_path, "rb")
        self._file_size = os.path.getsize(file_path)
        self._length = len(self._prefix) + self._file_size + len(self._suffix)
        self._pos = 0
        self._stage = "prefix"  # prefix -> file -> suffix

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        out = []
        remaining = size if size > 0 else None
        while True:
            if self._stage == "prefix":
                take = len(self._prefix) if remaining is None else min(remaining, len(self._prefix))
                if take:
                    out.append(self._prefix[:take])
                    self._prefix = self._prefix[take:]
                    self._pos += take
                    if remaining is not None:
                        remaining -= take
                        if remaining == 0:
                            return b"".join(out)
                if not self._prefix:
                    self._stage = "file"
            if self._stage == "file":
                chunk_size = 65536 if remaining is None or remaining > 65536 else remaining
                data = self._file.read(chunk_size)
                if data:
                    out.append(data)
                    self._pos += len(data)
                    if remaining is not None:
                        remaining -= len(data)
                        if remaining == 0:
                            return b"".join(out)
                else:
                    self._file.close()
                    self._stage = "suffix"
            if self._stage == "suffix":
                take = len(self._suffix) if remaining is None else min(remaining, len(self._suffix))
                if take:
                    out.append(self._suffix[:take])
                    self._suffix = self._suffix[take:]
                    self._pos += take
                    if remaining is not None:
                        remaining -= take
                        if remaining == 0:
                            return b"".join(out)
                if not self._suffix:
                    return b"".join(out) if out else b""
        return b"".join(out)

    def __len__(self):
        return self._length


def send_photo(file_path: str) -> bool:
    """
    Send a photo to the configured Telegram chat.
    file_path: path to an image file (e.g. .png).
    Streams the file in chunks to avoid loading the whole image into memory.
    Returns True if sent, False if not configured or on error.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----ClaudeCoinBoundary"
    reader = _MultipartPhotoReader(file_path, chat_id, boundary)
    try:
        req = urllib.request.Request(url, data=reader, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("Content-Length", str(len(reader)))
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False
    finally:
        if hasattr(reader, "_file") and reader._file and not reader._file.closed:
            reader._file.close()


def notify_trade(
    symbol: str,
    side: str,
    qty: int | float,
    order_id: str,
    paper: bool,
    *,
    pnl_dollars: float | None = None,
    account_summary: str | None = None,
) -> None:
    mode = "paper" if paper else "LIVE"
    msg = f"🔄 {mode} {side.upper()} {symbol} qty={qty} order_id={order_id}"
    if pnl_dollars is not None:
        sign = "+" if pnl_dollars >= 0 else ""
        msg += f"\n  P&L: {sign}${pnl_dollars:.2f}"
    if account_summary:
        msg += f"\n\n{account_summary}"
    send_message(msg)


def notify_account_status(summary: str) -> None:
    """Send account status (equity, cash, positions)."""
    send_message(f"📊 Account\n\n{summary}")


def notify_error(message: str) -> None:
    send_message(f"❌ Bot error: {message}")


if __name__ == "__main__":
    """Send a test message to verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."""
    env_path = Path(__file__).resolve().parent / ".env"
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _is_configured():
        print("Not configured. In .env add (no quotes, no spaces around =):")
        print("  TELEGRAM_BOT_TOKEN=your_token_from_botfather")
        print("  TELEGRAM_CHAT_ID=your_chat_id")
        if not token:
            print("  -> TELEGRAM_BOT_TOKEN is missing or empty")
        if not chat_id:
            print("  -> TELEGRAM_CHAT_ID is missing or empty")
        print(f"  (Loading .env from: {env_path})")
        exit(1)
    ok = send_message("✅ Claude Coin Telegram test — if you see this, alerts will work.")
    print("Sent." if ok else "Failed to send (check token and chat_id).")
    exit(0 if ok else 1)

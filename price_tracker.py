"""
price-tracker-bot
------------------
Tracks a cryptocurrency's price using the free public CoinGecko API
and sends a Telegram message whenever the price moves by more than
a set percentage.

How it works:
1. Every CHECK_INTERVAL_SECONDS seconds, the script asks CoinGecko
   for the current price of a coin.
2. It compares that price to the one from the last check (stored in
   a local file, last_price.json).
3. If the change is bigger than CHANGE_THRESHOLD_PERCENT, it sends a
   message through the Telegram Bot API.

Setup before running:
    1. Create a bot via @BotFather on Telegram -> get a BOT_TOKEN.
    2. Send your bot any message, then open in a browser:
       https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
       and look for "chat":{"id": ...} -> that's your CHAT_ID.
    3. Fill in both values below in the CONFIG section (or set the
       TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID environment variables).

Run:
    python price_tracker.py
The script runs in an endless loop. Stop it with Ctrl+C.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ======================= CONFIG =======================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "PASTE_YOUR_CHAT_ID_HERE")

COIN_ID = "bitcoin"              # CoinGecko coin id (bitcoin, ethereum, solana...)
VS_CURRENCY = "usd"              # currency to display the price in

CHANGE_THRESHOLD_PERCENT = 1.0   # notify when price moves by N% or more
CHECK_INTERVAL_SECONDS = 300     # how often to check the price (300s = 5 min)

STATE_FILE = "last_price.json"   # file where the last checked price is stored
# ========================================================

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def get_current_price(coin_id: str, vs_currency: str) -> float:
    """Requests the current coin price from the public CoinGecko API."""
    params = {"ids": coin_id, "vs_currencies": vs_currency}
    response = requests.get(COINGECKO_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if coin_id not in data or vs_currency not in data[coin_id]:
        raise ValueError(f"CoinGecko returned no price for '{coin_id}' in '{vs_currency}'. Check COIN_ID.")

    return float(data[coin_id][vs_currency])


def load_last_price() -> float | None:
    """Reads the price saved at the last check. Returns None if there isn't one yet."""
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("price")
    except (json.JSONDecodeError, OSError):
        # File is missing or corrupted -> treat as "no previous data"
        return None


def save_last_price(price: float) -> None:
    """Saves the current price to a local file for the next check."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"price": price, "saved_at": datetime.now(timezone.utc).isoformat()}, f)


def send_telegram_message(text: str) -> bool:
    """Sends a message through the Telegram Bot API. Returns True on success."""
    url = TELEGRAM_SEND_MESSAGE_URL.format(token=BOT_TOKEN)
    payload = {"chat_id": CHAT_ID, "text": text}

    try:
        response = requests.post(url, json=payload, timeout=10)
    except requests.RequestException as e:
        print(f"Could not reach Telegram: {e}", file=sys.stderr)
        return False

    if response.status_code != 200:
        print(f"Telegram returned an error {response.status_code}: {response.text}", file=sys.stderr)
        return False

    print("Notification sent to Telegram.")
    return True


def percent_change(old_price: float, new_price: float) -> float:
    """Calculates the price change as a percentage."""
    if old_price == 0:
        return 0.0
    return (new_price - old_price) / old_price * 100


def check_price_once() -> None:
    """One check: get the price, compare with the last one, notify if needed."""
    current_price = get_current_price(COIN_ID, VS_CURRENCY)
    last_price = load_last_price()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {COIN_ID}: {current_price} {VS_CURRENCY.upper()}")

    if last_price is None:
        print("First check - saving the current price as the baseline.")
        save_last_price(current_price)
        send_telegram_message(
            f"Started tracking {COIN_ID.upper()}.\nCurrent price: {current_price} {VS_CURRENCY.upper()}"
        )
        return

    change = percent_change(last_price, current_price)

    if abs(change) < CHANGE_THRESHOLD_PERCENT:
        print(f"Change of {change:.2f}% is below the {CHANGE_THRESHOLD_PERCENT}% threshold - no notification sent.")
        return

    direction = "went up" if change > 0 else "went down"
    message = (
        f"{COIN_ID.upper()} price {direction} by {change:.2f}%\n"
        f"Was: {last_price} {VS_CURRENCY.upper()}\n"
        f"Now: {current_price} {VS_CURRENCY.upper()}"
    )
    send_telegram_message(message)
    save_last_price(current_price)


def config_is_valid() -> bool:
    """Checks that BOT_TOKEN and CHAT_ID were set before starting."""
    if "PASTE_YOUR" in BOT_TOKEN or "PASTE_YOUR" in CHAT_ID:
        print(
            "Set BOT_TOKEN and CHAT_ID at the top of this file (CONFIG section), "
            "or via the TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID environment variables.",
            file=sys.stderr,
        )
        return False
    return True


def main() -> None:
    if not config_is_valid():
        sys.exit(1)

    print(f"Tracking {COIN_ID} every {CHECK_INTERVAL_SECONDS} sec. Press Ctrl+C to stop.")

    while True:
        try:
            check_price_once()
        except requests.RequestException as e:
            print(f"Network error while contacting CoinGecko: {e}", file=sys.stderr)
        except ValueError as e:
            print(f"Data error: {e}", file=sys.stderr)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

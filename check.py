import os
import time
import hashlib
import re
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Signals based on your screenshots
IN_STOCK_BUTTON_TEXTS = {
    "add",
    "add to bag",
    "add to basket",
}
OUT_OF_STOCK_TEXTS = {
    "out of stock",
    "sold out",
    "not available",
}

def telegram(msg: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    r.raise_for_status()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def extract_action_texts(soup: BeautifulSoup) -> list[str]:
    """
    Collect text from clickable purchase-related elements.
    Zara's DOM changes a lot, so we grab button-like elements broadly.
    """
    texts = []
    for el in soup.select("button, a[role='button'], div[role='button']"):
        t = norm(el.get_text(" ", strip=True))
        if not t:
            continue
        # Keep only short-ish action-ish texts to reduce noise
        if len(t) <= 60:
            texts.append(t)
    return texts

def is_in_stock_from_texts(action_texts: list[str]) -> bool | None:
    """
    Returns:
      True  -> looks in stock
      False -> looks out of stock
      None  -> can't tell (page layout or language differs)
    """
    joined = " | ".join(action_texts)

    # Strong out-of-stock signal (matches your screenshot where button includes "OUT OF STOCK")
    if any(oos in joined for oos in OUT_OF_STOCK_TEXTS):
        # If the page says out of stock anywhere in action area, treat as sold out.
        return False

    # Strong in-stock signal (your screenshot has a big "ADD" button)
    if any(re.search(rf"\b{re.escape(txt)}\b", joined) for txt in IN_STOCK_BUTTON_TEXTS):
        return True

    return None

def fetch_action_texts(url: str) -> list[str]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    return extract_action_texts(soup)

def main() -> None:
    with open("products.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    state_file = "state.txt"
    prev = {}
    if os.path.exists(state_file):
        for line in open(state_file, "r", encoding="utf-8"):
            k, v = line.rstrip("\n").split("\t")
            prev[k] = v

    new = {}
    notifications = []

    for url in urls:
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()

        try:
            action_texts = fetch_action_texts(url)
            status = is_in_stock_from_texts(action_texts)
        except Exception:
            status = None

        # Store state: 1=in stock, 0=out of stock, ?=unknown/error
        new_state = "1" if status is True else "0" if status is False else "?"
        new[key] = new_state

        # Notify only on transition to in-stock
        if status is True and prev.get(key) != "1":
            notifications.append(f"✅ Back in stock:\n{url}")

        time.sleep(2)  # be polite

    with open(state_file, "w", encoding="utf-8") as f:
        for k, v in new.items():
            f.write(f"{k}\t{v}\n")

    if notifications:
        telegram("\n\n".join(notifications))

if __name__ == "__main__":
    main()

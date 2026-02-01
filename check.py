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

# Based on your screenshots
IN_STOCK_MARKERS = [
    "add",
    "add to bag",
    "add to basket",
]
OUT_OF_STOCK_MARKERS = [
    "out of stock",
    "sold out",
    "not available",
    "view similar out of stock",  # sometimes Zara combines these
]

def telegram(msg: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    r.raise_for_status()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def extract_action_texts(soup: BeautifulSoup) -> list[str]:
    """
    Collect text from clickable elements.
    Zara's DOM changes often, so we grab "button-ish" elements broadly.
    """
    texts: list[str] = []
    for el in soup.select("button, a[role='button'], div[role='button']"):
        t = norm(el.get_text(" ", strip=True))
        if not t:
            continue
        if len(t) <= 80:
            texts.append(t)
    return texts

def fetch_page(url: str) -> tuple[list[str], str]:
    """
    Returns:
      - action_texts: texts from button-like elements
      - html_norm: normalized full HTML (fallback when button text is JS-rendered)
    """
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    action_texts = extract_action_texts(soup)
    html_norm = norm(html)
    return action_texts, html_norm

def contains_marker(text: str, markers: list[str]) -> bool:
    for m in markers:
        # word-boundary helps avoid accidental matches
        if re.search(rf"\b{re.escape(m)}\b", text):
            return True
    return False

def detect_stock(action_texts: list[str], html_norm: str) -> bool | None:
    """
    Returns:
      True  -> in stock (ADD detected)
      False -> out of stock detected
      None  -> can't tell
    """
    joined = " | ".join(action_texts)

    # Prefer signals from buttons/CTAs
    if contains_marker(joined, OUT_OF_STOCK_MARKERS):
        return False
    if contains_marker(joined, IN_STOCK_MARKERS):
        return True

    # Fallback: search entire HTML text (helps when Zara renders buttons via JS)
    if contains_marker(html_norm, OUT_OF_STOCK_MARKERS):
        return False
    if contains_marker(html_norm, IN_STOCK_MARKERS):
        return True

    return None

def load_prev_state(state_file: str) -> dict[str, str]:
    prev: dict[str, str] = {}
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                k, v = line.split("\t")
                prev[k] = v
    return prev

def save_state(state_file: str, new: dict[str, str]) -> None:
    with open(state_file, "w", encoding="utf-8") as f:
        for k, v in new.items():
            f.write(f"{k}\t{v}\n")

def main() -> None:
    # Read URLs
    with open("products.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    state_file = "state.txt"
    prev = load_prev_state(state_file)

    new: dict[str, str] = {}
    notifications: list[str] = []

    for url in urls:
        # stable key per URL
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()

        try:
            action_texts, html_norm = fetch_page(url)
            status = detect_stock(action_texts, html_norm)
        except Exception:
            status = None

        # Store state: 1=in stock, 0=out of stock, ?=unknown/error
        new_state = "1" if status is True else "0" if status is False else "?"
        new[key] = new_state

        # ✅ Notify when it becomes in stock (or first time tracked as in stock)
        if status is True and prev.get(key) != "1":
            notifications.append(f"✅ Back in stock (ADD available):\n{url}")

        # Be polite to Zara
        time.sleep(2)

    save_state(state_file, new)

    if notifications:
        telegram("\n\n".join(notifications))

if __name__ == "__main__":
    main()

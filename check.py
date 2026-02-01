import os
import time
import hashlib
import re
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Text signals (based on your screenshots)
IN_STOCK_MARKERS = ["add", "add to bag", "add to basket"]
OUT_OF_STOCK_MARKERS = ["out of stock", "sold out", "not available", "view similar out of stock"]

def telegram(msg: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    r.raise_for_status()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def contains_marker(text: str, markers: list[str]) -> bool:
    for m in markers:
        if re.search(rf"\b{re.escape(m)}\b", text):
            return True
    return False

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

def detect_stock_with_browser(page, url: str) -> bool | None:
    """
    Loads the page with JS enabled and checks visible text for stock signals.
    Returns: True (in stock), False (out of stock), None (can't tell)
    """
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Wait a bit for JS to render buttons (Zara can be slow)
    page.wait_for_timeout(4000)

    # Grab visible page text
    text = norm(page.inner_text("body"))

    # Decide
    if contains_marker(text, OUT_OF_STOCK_MARKERS):
        return False
    if contains_marker(text, IN_STOCK_MARKERS):
        return True

    return None

def main() -> None:
    with open("products.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    state_file = "state.txt"
    prev = load_prev_state(state_file)

    new: dict[str, str] = {}
    notifications: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            locale="en-US",
        )
        page = context.new_page()

        for url in urls:
            key = hashlib.sha1(url.encode("utf-8")).hexdigest()

            try:
                status = detect_stock_with_browser(page, url)
            except Exception:
                status = None

            # 1=in stock, 0=out of stock, ?=unknown
            new_state = "1" if status is True else "0" if status is False else "?"
            new[key] = new_state

            # Notify when it becomes in stock (or first time tracked as in stock)
            if status is True and prev.get(key) != "1":
                notifications.append(f"✅ Back in stock (ADD available):\n{url}")

            time.sleep(2)  # be polite

        context.close()
        browser.close()

    save_state(state_file, new)

    if notifications:
        telegram("\n\n".join(notifications))

if __name__ == "__main__":
    main()

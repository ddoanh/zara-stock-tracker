import os
import time
import hashlib
import re
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DEBUG = os.environ.get("DEBUG", "0") == "1"

# Based on your screenshots
IN_STOCK_MARKERS = ["add", "add to bag", "add to basket"]
OUT_OF_STOCK_MARKERS = ["out of stock", "sold out", "not available", "view similar out of stock"]

def telegram(msg: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    r.raise_for_status()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def contains_any(text: str, markers: list[str]) -> bool:
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
                # format: key \t state
                parts = line.split("\t")
                if len(parts) >= 2:
                    prev[parts[0]] = parts[1]
    return prev

def save_state(state_file: str, new: dict[str, str]) -> None:
    with open(state_file, "w", encoding="utf-8") as f:
        for k, v in new.items():
            f.write(f"{k}\t{v}\n")

def detect_stock(page, url: str) -> tuple[bool | None, str]:
    """
    Returns (status, evidence_text)
      status: True=in stock, False=out of stock, None=unknown
      evidence_text: short debug snippet
    """
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)

    body_text = norm(page.inner_text("body"))

    # Try strict decision first
    if contains_any(body_text, OUT_OF_STOCK_MARKERS):
        return False, "matched out-of-stock marker in body text"
    if contains_any(body_text, IN_STOCK_MARKERS):
        return True, "matched in-stock marker in body text"

    # If still unknown, return a small snippet to debug
    snippet = body_text[:400]
    return None, f"no markers found; snippet={snippet!r}"

def main() -> None:
    with open("products.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    prev = load_prev_state("state.txt")
    new: dict[str, str] = {}
    notifications: list[str] = []

    # Optional one-time test (remove after you’re done troubleshooting)
    # telegram("🧪 Zara checker started a run")

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
                status, evidence = detect_stock(page, url)
            except Exception as e:
                status, evidence = None, f"exception: {e!r}"

            state = "1" if status is True else "0" if status is False else "?"
            new[key] = state

            if DEBUG:
                print("URL:", url)
                print("STATE:", state)
                print("EVIDENCE:", evidence)
                print("-" * 60)

            # Notify on transition to in-stock
            if status is True and prev.get(key) != "1":
                notifications.append(f"✅ Back in stock (ADD available):\n{url}")

            time.sleep(1)

        context.close()
        browser.close()

    save_state("state.txt", new)

    if notifications:
        telegram("\n\n".join(notifications))

if __name__ == "__main__":
    main()

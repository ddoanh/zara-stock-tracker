import os, time, hashlib
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; restock-check/1.0)"
}

OUT_OF_STOCK_MARKERS = [
    "out of stock",
    "sold out",
    "agotado",
    "épuisé",
    "esaurito",
    "nicht verfügbar",
    "sin stock",
]

IN_STOCK_MARKERS = [
    "add to bag",
    "add to basket",
    "añadir",
    "ajouter",
    "in den warenkorb",
]

def telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    r.raise_for_status()

def normalize(text: str) -> str:
    return " ".join(text.lower().split())

def check_url(url: str) -> bool:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = normalize(r.text)

    # crude but effective heuristic:
    oos = any(m in html for m in OUT_OF_STOCK_MARKERS)
    instock = any(m in html for m in IN_STOCK_MARKERS)

    # If it contains “add to bag/basket” markers and NOT out-of-stock markers, treat as available.
    return instock and not oos

def main():
    with open("products.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    # Keep a small “state” so we only notify on changes.
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
            available = check_url(url)
        except Exception as e:
            # skip temporary failures quietly
            available = None

        new[key] = "1" if available else "0" if available is False else "?"

        if available is True and prev.get(key) != "1":
            notifications.append(f"✅ Back in stock (detected):\n{url}")

        time.sleep(2)  # be polite

    with open(state_file, "w", encoding="utf-8") as f:
        for k, v in new.items():
            f.write(f"{k}\t{v}\n")

    if notifications:
        telegram("\n\n".join(notifications))

if __name__ == "__main__":
    main()

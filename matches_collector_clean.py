import requests
import csv
import time
import os

URL = "https://api.bitpin.org/api/v1/mth/matches/SOL_USDT/"
FILE = "matches_clean.csv"

seen = set()

if os.path.exists(FILE):
    with open(FILE, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("id"):
                seen.add(row["id"])

print("Starting CLEAN SOL_USDT matches collector...")
print("Existing unique IDs:", len(seen))
print("Press CTRL+C to stop.")
print("")

while True:
    try:
        r = requests.get(URL, timeout=10)

        if r.status_code != 200:
            print("HTTP ERROR:", r.status_code)
            time.sleep(5)
            continue

        matches = r.json()
        new_count = 0

        file_exists = os.path.exists(FILE)

        with open(FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow([
                    "id",
                    "time",
                    "price",
                    "base_amount",
                    "quote_amount",
                    "side"
                ])

            for x in reversed(matches):
                trade_id = x.get("id")

                if not trade_id or trade_id in seen:
                    continue

                writer.writerow([
                    trade_id,
                    x.get("time"),
                    x.get("price"),
                    x.get("base_amount"),
                    x.get("quote_amount"),
                    x.get("side")
                ])

                seen.add(trade_id)
                new_count += 1

        print(
            "API:", len(matches),
            "| NEW:", new_count,
            "| TOTAL UNIQUE:", len(seen),
            "| Last:", matches[0].get("price") if matches else "-",
            "| Side:", matches[0].get("side") if matches else "-"
        )

        time.sleep(5)

    except KeyboardInterrupt:
        print("")
        print("Collector stopped.")
        break

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
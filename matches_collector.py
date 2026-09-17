import requests
import csv
import time
import os

URL = "https://api.bitpin.org/api/v1/mth/matches/SOL_USDT/"

FILE = "matches_data.csv"

print("Starting SOL_USDT matches collector...")
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

                writer.writerow([
                    x.get("id"),
                    x.get("time"),
                    x.get("price"),
                    x.get("base_amount"),
                    x.get("quote_amount"),
                    x.get("side")
                ])

        print(
            "Collected:",
            len(matches),
            "| Last:",
            matches[0]["price"],
            "| Side:",
            matches[0]["side"]
        )

        time.sleep(5)

    except KeyboardInterrupt:

        print("")
        print("Collector stopped.")
        break

    except Exception as e:

        print("ERROR:", e)
        time.sleep(5)
import csv
from datetime import datetime

data = {}

with open("market_data.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        try:
            t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S")
            data.setdefault(r["symbol"], []).append({
                "t": t,
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"])
            })
        except:
            pass

for symbol, rows in data.items():
    correct = 0
    total = 0

    for i in range(5, len(rows) - 1):
        mid = rows[i]["mid"]

        old_mid = rows[i-5]["mid"]
        momentum = (mid - old_mid) / old_mid * 100

        future = rows[i+1]["mid"]

        move = (future - mid) / mid * 100

        if move == 0:
            continue

        score = rows[i]["obi"] + rows[i]["ofi"] + momentum

        if score == 0:
            continue

        predicted = 1 if score > 0 else -1
        actual = 1 if move > 0 else -1

        total += 1

        if predicted == actual:
            correct += 1

    if total:
        print(
            symbol,
            "Samples:", total,
            "Accuracy:", round(correct / total * 100, 2), "%"
        )
    else:
        print(symbol, "No usable samples")
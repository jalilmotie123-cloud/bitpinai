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


HORIZONS = [1, 3, 5]

for symbol, rows in data.items():

    print("\n" + "=" * 50)
    print(symbol)
    print("=" * 50)

    for horizon in HORIZONS:

        normal_correct = 0
        reverse_correct = 0
        total = 0

        for i in range(5, len(rows) - horizon):

            mid = rows[i]["mid"]
            old_mid = rows[i - 5]["mid"]

            momentum = (mid - old_mid) / old_mid * 100

            future = rows[i + horizon]["mid"]
            move = (future - mid) / mid * 100

            if abs(move) < 0.02:
                continue

            obi = max(-1, min(1, rows[i]["obi"]))
            ofi = max(-1, min(1, rows[i]["ofi"]))
            momentum_score = max(-1, min(1, momentum / 0.1))

            score = (
                obi * 0.40 +
                ofi * 0.35 +
                momentum_score * 0.25
            )

            if abs(score) < 0.20:
                continue

            predicted = 1 if score > 0 else -1
            actual = 1 if move > 0 else -1

            total += 1

            if predicted == actual:
                normal_correct += 1

            if predicted != actual:
                reverse_correct += 1

        if total:

            normal_accuracy = normal_correct / total * 100
            reverse_accuracy = reverse_correct / total * 100

            print(
                "Horizon:", horizon,
                "| Samples:", total,
                "| Normal:", round(normal_accuracy, 2), "%",
                "| Reverse:", round(reverse_accuracy, 2), "%"
            )

        else:
            print(
                "Horizon:", horizon,
                "| No usable signals"
            )
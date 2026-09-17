
import csv
from datetime import datetime

data = {}

with open("market_data.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if not r["obi10"] or not r["flow_imbalance"]:
            continue

        t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S")
        mid = float(r["mid"])
        obi = float(r["obi10"])
        flow = float(r["flow_imbalance"])
        spread = float(r["spread_pct"])

        data.setdefault(r["symbol"], []).append(
            (t, mid, obi, flow, spread)
        )

for symbol, rows in data.items():
    correct = 0
    total = 0

    for i, (t, mid, obi, flow, spread) in enumerate(rows):
        future = None

        for j in range(i + 1, len(rows)):
            if (rows[j][0] - t).total_seconds() >= 25:
                future = rows[j][1]
                break

        if future is None:
            continue

        move = future - mid

        if move == 0:
            continue

        score = obi + flow

        if abs(score) < 0.1:
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
            "Combined Accuracy:",
            round(correct / total * 100, 2), "%"
        )
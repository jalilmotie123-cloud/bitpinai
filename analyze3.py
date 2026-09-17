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

        data.setdefault(r["symbol"], []).append((t, mid, obi, flow))

for symbol, rows in data.items():
    correct = 0
    total = 0

    for i in range(5, len(rows)):
        t, mid, obi, flow = rows[i]

        old_mid = rows[i-5][1]
        old_obi = rows[i-5][2]
        old_flow = rows[i-5][3]

        price_change = (mid - old_mid) / old_mid * 100
        obi_change = obi - old_obi
        flow_change = flow - old_flow

        score = obi + flow + obi_change + flow_change + price_change

        if abs(score) < 0.1:
            continue

        future = None

        for j in range(i + 1, len(rows)):
            if (rows[j][0] - t).total_seconds() >= 25:
                future = rows[j][1]
                break

        if future is None or future == mid:
            continue

        predicted = 1 if score > 0 else -1
        actual = 1 if future > mid else -1

        total += 1

        if predicted == actual:
            correct += 1

    if total:
        print(symbol,
              "Samples:", total,
              "Accuracy:", round(correct / total * 100, 2), "%")
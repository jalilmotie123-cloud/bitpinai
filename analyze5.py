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


# بررسی چند افق آینده
HORIZONS = [1, 3, 5]

for symbol, rows in data.items():

    print("\n" + "=" * 45)
    print(symbol)
    print("=" * 45)

    for horizon in HORIZONS:

        correct = 0
        total = 0
        skipped = 0

        for i in range(5, len(rows) - horizon):

            mid = rows[i]["mid"]

            old_mid = rows[i - 5]["mid"]

            momentum = (mid - old_mid) / old_mid * 100

            future = rows[i + horizon]["mid"]

            move = (future - mid) / mid * 100

            # حذف حرکات بسیار کوچک
            if abs(move) < 0.02:
                skipped += 1
                continue

            obi = rows[i]["obi"]
            ofi = rows[i]["ofi"]

            # نرمال‌سازی ساده برای جلوگیری از غلبه یک شاخص
            obi_score = max(-1, min(1, obi))
            ofi_score = max(-1, min(1, ofi))
            momentum_score = max(-1, min(1, momentum / 0.1))

            # امتیاز نهایی
            score = (
                obi_score * 0.40 +
                ofi_score * 0.35 +
                momentum_score * 0.25
            )

            # حذف سیگنال‌های ضعیف
            if abs(score) < 0.20:
                skipped += 1
                continue

            predicted = 1 if score > 0 else -1
            actual = 1 if move > 0 else -1

            total += 1

            if predicted == actual:
                correct += 1

        if total > 0:
            accuracy = correct / total * 100

            print(
                "Horizon:",
                horizon,
                "Samples:",
                total,
                "Accuracy:",
                round(accuracy, 2),
                "%",
                "Skipped:",
                skipped
            )

        else:
            print(
                "Horizon:",
                horizon,
                "No usable signals"
            )
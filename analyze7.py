import csv
from datetime import datetime

data = {}

with open("market_data.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        try:
            data.setdefault(r["symbol"], []).append({
                "t": datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S"),
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"])
            })
        except:
            pass


HORIZONS = [1, 3, 5]
TRAIN_RATIO = 0.70

for symbol, rows in data.items():

    # مرتب‌سازی زمانی
    rows.sort(key=lambda x: x["t"])

    split = int(len(rows) * TRAIN_RATIO)

    print("\n" + "=" * 60)
    print(symbol)
    print("Total rows:", len(rows))
    print("Train rows:", split)
    print("Test rows:", len(rows) - split)
    print("=" * 60)

    for horizon in HORIZONS:

        # ---------- TRAIN ----------
        normal_correct_train = 0
        reverse_correct_train = 0
        train_total = 0

        for i in range(5, split - horizon):

            mid = rows[i]["mid"]
            old_mid = rows[i - 5]["mid"]
            future = rows[i + horizon]["mid"]

            momentum = (mid - old_mid) / old_mid * 100
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

            train_total += 1

            if predicted == actual:
                normal_correct_train += 1

            if predicted != actual:
                reverse_correct_train += 1

        # انتخاب جهت فقط با TRAIN
        if train_total == 0:
            print("Horizon:", horizon, "| No train signals")
            continue

        normal_train = normal_correct_train / train_total * 100
        reverse_train = reverse_correct_train / train_total * 100

        if reverse_train > normal_train:
            selected_mode = "REVERSE"
        else:
            selected_mode = "NORMAL"

        # ---------- TEST ----------
        test_correct = 0
        test_total = 0

        for i in range(max(5, split), len(rows) - horizon):

            mid = rows[i]["mid"]
            old_mid = rows[i - 5]["mid"]
            future = rows[i + horizon]["mid"]

            momentum = (mid - old_mid) / old_mid * 100
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

            if selected_mode == "REVERSE":
                predicted *= -1

            actual = 1 if move > 0 else -1

            test_total += 1

            if predicted == actual:
                test_correct += 1

        if test_total:
            test_accuracy = test_correct / test_total * 100

            print(
                "Horizon:", horizon,
                "| Train Normal:", round(normal_train, 2), "%",
                "| Train Reverse:", round(reverse_train, 2), "%",
                "| Selected:", selected_mode,
                "| TEST Samples:", test_total,
                "| TEST Accuracy:", round(test_accuracy, 2), "%"
            )
        else:
            print(
                "Horizon:", horizon,
                "| Selected:", selected_mode,
                "| No test signals"
            )
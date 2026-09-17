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


HORIZON = 5

# اندازه پنجره آموزش و تعداد بخش‌های Walk-Forward
TRAIN_SIZE = 600
TEST_SIZE = 200

for symbol, rows in data.items():

    rows.sort(key=lambda x: x["t"])

    n = len(rows)

    print("\n" + "=" * 70)
    print(symbol)
    print("Total rows:", n)
    print("=" * 70)

    all_correct = 0
    all_total = 0
    all_selected_modes = []

    start = TRAIN_SIZE

    window_number = 0

    while start < n:

        train_start = start - TRAIN_SIZE
        train_end = start
        test_start = start
        test_end = min(start + TEST_SIZE, n)

        # ---------------- TRAIN ----------------

        normal_correct = 0
        reverse_correct = 0
        train_total = 0

        for i in range(max(train_start, 5), train_end - HORIZON):

            mid = rows[i]["mid"]
            old_mid = rows[i - 5]["mid"]
            future = rows[i + HORIZON]["mid"]

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
                normal_correct += 1

            if predicted != actual:
                reverse_correct += 1

        if train_total == 0:
            start += TEST_SIZE
            continue

        normal_acc = normal_correct / train_total * 100
        reverse_acc = reverse_correct / train_total * 100

        if reverse_acc > normal_acc:
            mode = "REVERSE"
        else:
            mode = "NORMAL"

        all_selected_modes.append(mode)

        # ---------------- TEST ----------------

        test_correct = 0
        test_total = 0

        for i in range(max(test_start, 5), test_end - HORIZON):

            mid = rows[i]["mid"]
            old_mid = rows[i - 5]["mid"]
            future = rows[i + HORIZON]["mid"]

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

            if mode == "REVERSE":
                predicted *= -1

            actual = 1 if move > 0 else -1

            test_total += 1

            if predicted == actual:
                test_correct += 1

        if test_total:

            accuracy = test_correct / test_total * 100

            all_correct += test_correct
            all_total += test_total

            window_number += 1

            print(
                "Window:", window_number,
                "| Train:", train_total,
                "| Mode:", mode,
                "| Test:", test_total,
                "| Accuracy:", round(accuracy, 2), "%"
            )

        start += TEST_SIZE

    # ---------------- FINAL RESULT ----------------

    if all_total:

        overall_accuracy = all_correct / all_total * 100

        normal_count = all_selected_modes.count("NORMAL")
        reverse_count = all_selected_modes.count("REVERSE")

        print("-" * 70)
        print("FINAL")
        print("Total Test Signals:", all_total)
        print("Total Correct:", all_correct)
        print("Overall Accuracy:", round(overall_accuracy, 2), "%")
        print("NORMAL windows:", normal_count)
        print("REVERSE windows:", reverse_count)

    else:
        print("No usable walk-forward test signals.")
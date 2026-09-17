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
SEGMENTS = 4

for symbol, rows in data.items():

    rows.sort(key=lambda x: x["t"])

    n = len(rows)
    segment_size = n // SEGMENTS

    print("\n" + "=" * 65)
    print(symbol)
    print("Total rows:", n)
    print("=" * 65)

    for seg in range(SEGMENTS):

        start = seg * segment_size
        end = (seg + 1) * segment_size if seg < SEGMENTS - 1 else n

        # برای هر بازه، جهت را فقط از 70٪ ابتدایی همان بازه یاد می‌گیریم
        train_end = start + int((end - start) * 0.70)

        normal_correct_train = 0
        reverse_correct_train = 0
        train_total = 0

        # ---------- TRAIN ----------
        for i in range(max(start, 5), train_end - HORIZON):

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
                normal_correct_train += 1

            if predicted != actual:
                reverse_correct_train += 1

        if train_total == 0:
            print("Segment", seg + 1, "| No train signals")
            continue

        normal_train = normal_correct_train / train_total * 100
        reverse_train = reverse_correct_train / train_total * 100

        selected_mode = (
            "REVERSE"
            if reverse_train > normal_train
            else "NORMAL"
        )

        # ---------- TEST ----------
        test_correct = 0
        test_total = 0

        for i in range(max(train_end, 5), end - HORIZON):

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

            if selected_mode == "REVERSE":
                predicted *= -1

            actual = 1 if move > 0 else -1

            test_total += 1

            if predicted == actual:
                test_correct += 1

        if test_total:
            accuracy = test_correct / test_total * 100

            print(
                "Segment", seg + 1,
                "| Train:", train_total,
                "| Mode:", selected_mode,
                "| TEST:", test_total,
                "| Accuracy:", round(accuracy, 2), "%"
            )
        else:
            print(
                "Segment", seg + 1,
                "| Mode:", selected_mode,
                "| No test signals"
            )
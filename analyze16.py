import csv
from collections import defaultdict
from datetime import datetime
from statistics import mean, median


FILE = "market_data.csv"

HORIZONS = [5, 15, 30]

PERCENTILE = 0.10


def pct_change(old_price, new_price):
    if old_price == 0:
        return 0.0
    return (new_price - old_price) / old_price * 100.0


def percentile(sorted_values, p):
    """
    Linear percentile without external libraries.
    p must be between 0 and 1.
    """
    if not sorted_values:
        return 0.0

    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * p
    lower = int(position)
    upper = lower + 1

    if upper >= len(sorted_values):
        return sorted_values[-1]

    weight = position - lower

    return (
        sorted_values[lower]
        * (1.0 - weight)
        + sorted_values[upper]
        * weight
    )


def calculate_signal(items, i):
    if i < 5:
        return 0.0

    current_mid = items[i]["mid"]
    old_mid = items[i - 5]["mid"]

    if old_mid == 0:
        return 0.0

    momentum = (
        (current_mid - old_mid)
        / old_mid
        * 100.0
    )

    return (
        items[i]["obi10"]
        + items[i]["ofi_norm"]
        + momentum
    )


def summarize(name, records):

    print("\n" + name)

    if not records:
        print("Signals: 0")
        return

    moves = [x["move"] for x in records]
    spreads = [x["spread"] for x in records]

    positive = sum(1 for x in moves if x > 0)
    negative = sum(1 for x in moves if x < 0)
    flat = sum(1 for x in moves if x == 0)

    print("Signals:", len(records))

    print(
        "Signal strength min:",
        round(min(x["signal"] for x in records), 4)
    )

    print(
        "Signal strength max:",
        round(max(x["signal"] for x in records), 4)
    )

    print(
        "Avg future move (%):",
        round(mean(moves), 4)
    )

    print(
        "Median future move (%):",
        round(median(moves), 4)
    )

    print(
        "Avg absolute move (%):",
        round(mean(abs(x) for x in moves), 4)
    )

    print(
        "Positive (%):",
        round(positive / len(moves) * 100.0, 2)
    )

    print(
        "Negative (%):",
        round(negative / len(moves) * 100.0, 2)
    )

    print(
        "Flat (%):",
        round(flat / len(moves) * 100.0, 2)
    )

    print(
        "Avg spread (%):",
        round(mean(spreads), 4)
    )

    print(
        "Avg move minus spread (%):",
        round(
            mean(moves) - mean(spreads),
            4
        )
    )


def main():

    try:
        with open(
            FILE,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as f:
            rows = list(csv.DictReader(f))

    except Exception as e:
        print("ERROR reading file:", e)
        return

    data = defaultdict(list)

    for row in rows:
        try:
            data[row["symbol"]].append({
                "time": datetime.strptime(
                    row["time"],
                    "%Y-%m-%d %H:%M:%S"
                ),
                "mid": float(row["mid"]),
                "obi10": float(row["obi10"]),
                "ofi_norm": float(row["ofi_norm"]),
                "spread": float(row["spread_pct"])
            })
        except Exception:
            continue

    print("=" * 95)
    print("PERCENTILE SIGNAL TEST")
    print("File:", FILE)
    print("Top / Bottom:", int(PERCENTILE * 100), "%")
    print("=" * 95)

    for symbol in sorted(data):

        items = data[symbol]

        print("\n" + "#" * 95)
        print("SYMBOL:", symbol)
        print("ROWS:", len(items))
        print("#" * 95)

        for horizon in HORIZONS:

            observations = []

            for i in range(5, len(items) - horizon):

                signal = calculate_signal(items, i)

                current = items[i]
                future = items[i + horizon]

                move = pct_change(
                    current["mid"],
                    future["mid"]
                )

                observations.append({
                    "signal": signal,
                    "move": move,
                    "spread": current["spread"]
                })

            if not observations:
                continue

            signals = sorted(
                x["signal"]
                for x in observations
            )

            lower_threshold = percentile(
                signals,
                PERCENTILE
            )

            upper_threshold = percentile(
                signals,
                1.0 - PERCENTILE
            )

            strong_short = [
                x for x in observations
                if x["signal"] <= lower_threshold
            ]

            strong_long = [
                x for x in observations
                if x["signal"] >= upper_threshold
            ]

            print("\n" + "-" * 80)
            print("HORIZON:", horizon)
            print("Total observations:", len(observations))

            print(
                "LONG percentile threshold:",
                round(upper_threshold, 4)
            )

            print(
                "SHORT percentile threshold:",
                round(lower_threshold, 4)
            )

            summarize(
                "TOP 10% LONG",
                strong_long
            )

            summarize(
                "BOTTOM 10% SHORT",
                strong_short
            )

    print("\n" + "=" * 95)
    print("PERCENTILE SIGNAL TEST FINISHED")
    print("=" * 95)


if __name__ == "__main__":
    main()
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


def percentile(values, p):
    values = sorted(values)

    if not values:
        return 0.0

    if len(values) == 1:
        return values[0]

    pos = (len(values) - 1) * p
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    weight = pos - low

    return (
        values[low] * (1.0 - weight)
        + values[high] * weight
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


def analyze_long(records):
    if not records:
        return

    directional = [
        r["move"]
        for r in records
        if r["move"] != 0
    ]

    net_after_spread = [
        r["move"] - r["spread"]
        for r in records
    ]

    wins = sum(
        1 for r in records
        if r["move"] > r["spread"]
    )

    print("\nTOP 10% LONG")
    print("Signals:", len(records))

    print(
        "Signal range:",
        round(min(r["signal"] for r in records), 4),
        "to",
        round(max(r["signal"] for r in records), 4)
    )

    print(
        "Avg future move (%):",
        round(mean(r["move"] for r in records), 4)
    )

    print(
        "Median future move (%):",
        round(median(r["move"] for r in records), 4)
    )

    print(
        "Positive direction (%):",
        round(
            sum(1 for x in directional if x > 0)
            / len(records) * 100,
            2
        )
    )

    print(
        "Avg spread (%):",
        round(mean(r["spread"] for r in records), 4)
    )

    print(
        "Avg after-spread result (%):",
        round(mean(net_after_spread), 4)
    )

    print(
        "Trades beating spread (%):",
        round(
            wins / len(records) * 100,
            2
        )
    )


def analyze_short(records):
    if not records:
        return

    # برای SHORT حرکت مطلوب = منفی حرکت قیمت
    directional_results = [
        -r["move"]
        for r in records
    ]

    net_after_spread = [
        (-r["move"]) - r["spread"]
        for r in records
    ]

    wins = sum(
        1 for r in records
        if (-r["move"]) > r["spread"]
    )

    print("\nBOTTOM 10% SHORT")
    print("Signals:", len(records))

    print(
        "Signal range:",
        round(min(r["signal"] for r in records), 4),
        "to",
        round(max(r["signal"] for r in records), 4)
    )

    print(
        "Avg directional move (%):",
        round(mean(directional_results), 4)
    )

    print(
        "Median directional move (%):",
        round(median(directional_results), 4)
    )

    print(
        "Correct direction (%):",
        round(
            sum(1 for x in directional_results if x > 0)
            / len(records) * 100,
            2
        )
    )

    print(
        "Avg spread (%):",
        round(mean(r["spread"] for r in records), 4)
    )

    print(
        "Avg after-spread result (%):",
        round(mean(net_after_spread), 4)
    )

    print(
        "Trades beating spread (%):",
        round(
            wins / len(records) * 100,
            2
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
    print("CORRECTED PERCENTILE SIGNAL TEST")
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

                move = pct_change(
                    items[i]["mid"],
                    items[i + horizon]["mid"]
                )

                observations.append({
                    "signal": signal,
                    "move": move,
                    "spread": items[i]["spread"]
                })

            if not observations:
                continue

            signals = [
                x["signal"]
                for x in observations
            ]

            lower = percentile(
                signals,
                PERCENTILE
            )

            upper = percentile(
                signals,
                1.0 - PERCENTILE
            )

            long_records = [
                x for x in observations
                if x["signal"] >= upper
            ]

            short_records = [
                x for x in observations
                if x["signal"] <= lower
            ]

            print("\n" + "-" * 80)
            print("HORIZON:", horizon)
            print("Total observations:", len(observations))

            print(
                "LONG threshold:",
                round(upper, 4)
            )

            print(
                "SHORT threshold:",
                round(lower, 4)
            )

            analyze_long(long_records)
            analyze_short(short_records)

    print("\n" + "=" * 95)
    print("CORRECTED TEST FINISHED")
    print("=" * 95)


if __name__ == "__main__":
    main()
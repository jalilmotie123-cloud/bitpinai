import csv
from collections import defaultdict
from datetime import datetime
from statistics import mean, median


FILE = "market_data.csv"

HORIZONS = [5, 15, 30]

SIGNAL_THRESHOLD = 0.20


def pct_change(old_price, new_price):
    if old_price == 0:
        return 0.0
    return (new_price - old_price) / old_price * 100.0


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


def print_signal_group(name, moves, spreads):

    if not moves:
        print("\n", name)
        print("Signals: 0")
        return

    positive = sum(1 for x in moves if x > 0)
    negative = sum(1 for x in moves if x < 0)
    flat = sum(1 for x in moves if x == 0)

    print("\n", name)
    print("Signals:", len(moves))

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
        "Max move (%):",
        round(max(moves), 4)
    )

    print(
        "Min move (%):",
        round(min(moves), 4)
    )

    print(
        "Positive (%):",
        round(positive / len(moves) * 100, 2)
    )

    print(
        "Negative (%):",
        round(negative / len(moves) * 100, 2)
    )

    print(
        "Flat (%):",
        round(flat / len(moves) * 100, 2)
    )

    print(
        "Avg spread (%):",
        round(mean(spreads), 4)
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
                "spread": float(row["spread_pct"]),
                "obi10": float(row["obi10"]),
                "ofi_norm": float(row["ofi_norm"]),
            })
        except Exception:
            continue

    print("=" * 95)
    print("SIGNAL DIRECTION DIAGNOSTIC")
    print("File:", FILE)
    print("Signal threshold:", SIGNAL_THRESHOLD)
    print("=" * 95)

    for symbol in sorted(data):

        items = data[symbol]

        print("\n" + "#" * 95)
        print("SYMBOL:", symbol)
        print("ROWS:", len(items))
        print("#" * 95)

        for horizon in HORIZONS:

            long_moves = []
            long_spreads = []

            short_moves = []
            short_spreads = []

            no_signal = 0

            for i in range(5, len(items) - horizon):

                signal = calculate_signal(items, i)

                current = items[i]
                future = items[i + horizon]

                future_move = pct_change(
                    current["mid"],
                    future["mid"]
                )

                if signal >= SIGNAL_THRESHOLD:

                    long_moves.append(future_move)
                    long_spreads.append(
                        current["spread"]
                    )

                elif signal <= -SIGNAL_THRESHOLD:

                    short_moves.append(-future_move)
                    short_spreads.append(
                        current["spread"]
                    )

                else:
                    no_signal += 1

            print("\n" + "-" * 80)
            print("HORIZON:", horizon)

            print_signal_group(
                "LONG SIGNAL",
                long_moves,
                long_spreads
            )

            print_signal_group(
                "SHORT SIGNAL",
                short_moves,
                short_spreads
            )

            print(
                "\nNo signal:",
                no_signal
            )

    print("\n" + "=" * 95)
    print("SIGNAL DIAGNOSTIC FINISHED")
    print("=" * 95)


if __name__ == "__main__":
    main()
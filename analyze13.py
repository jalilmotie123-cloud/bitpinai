import csv
from collections import defaultdict
from datetime import datetime
from statistics import mean, median


FILE = "market_data.csv"
HORIZONS = [5, 15, 30]


def pct_change(old_price, new_price):
    if old_price == 0:
        return 0.0
    return (new_price - old_price) / old_price * 100.0


def main():
    try:
        with open(FILE, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        print("ERROR reading file:", e)
        return

    if not rows:
        print("ERROR: file is empty")
        return

    data = defaultdict(list)

    for row in rows:
        try:
            symbol = row["symbol"]
            t = datetime.strptime(
                row["time"],
                "%Y-%m-%d %H:%M:%S"
            )
            mid = float(row["mid"])
            spread = float(row["spread_pct"])

            data[symbol].append({
                "time": t,
                "mid": mid,
                "spread": spread
            })

        except Exception:
            continue

    print("=" * 90)
    print("FULL MARKET DATA HORIZON ANALYSIS")
    print("File:", FILE)
    print("Total CSV rows:", len(rows))
    print("Horizons:", HORIZONS)
    print("=" * 90)

    for symbol in sorted(data.keys()):

        items = data[symbol]

        print("\n" + "#" * 90)
        print("SYMBOL:", symbol)
        print("ROWS:", len(items))
        print("#" * 90)

        for horizon in HORIZONS:

            if len(items) <= horizon:
                print("\nHORIZON:", horizon)
                print("NOT ENOUGH DATA")
                continue

            moves = []
            abs_moves = []
            spreads = []
            durations = []

            for i in range(len(items) - horizon):

                current = items[i]
                future = items[i + horizon]

                move = pct_change(
                    current["mid"],
                    future["mid"]
                )

                moves.append(move)
                abs_moves.append(abs(move))
                spreads.append(current["spread"])

                seconds = (
                    future["time"] -
                    current["time"]
                ).total_seconds()

                if seconds >= 0:
                    durations.append(seconds)

            total = len(moves)

            positive = sum(
                1 for x in moves
                if x > 0
            )

            negative = sum(
                1 for x in moves
                if x < 0
            )

            flat = sum(
                1 for x in moves
                if x == 0
            )

            avg_move = mean(moves)
            avg_abs_move = mean(abs_moves)
            avg_spread = mean(spreads)

            ratio = (
                avg_abs_move / avg_spread
                if avg_spread > 0 else 0
            )

            print("\nHORIZON:", horizon)

            if durations:
                print(
                    "Approx time (sec):",
                    round(median(durations), 1)
                )

            print(
                "Samples:",
                total
            )

            print(
                "Avg spread (%):",
                round(avg_spread, 4)
            )

            print(
                "Median spread (%):",
                round(median(spreads), 4)
            )

            print(
                "Avg move (%):",
                round(avg_move, 4)
            )

            print(
                "Median move (%):",
                round(median(moves), 4)
            )

            print(
                "Avg absolute move (%):",
                round(avg_abs_move, 4)
            )

            print(
                "Max favorable move (%):",
                round(max(moves), 4)
            )

            print(
                "Min move (%):",
                round(min(moves), 4)
            )

            print(
                "Positive (%):",
                round(
                    positive / total * 100,
                    2
                )
            )

            print(
                "Negative (%):",
                round(
                    negative / total * 100,
                    2
                )
            )

            print(
                "Flat (%):",
                round(
                    flat / total * 100,
                    2
                )
            )

            print(
                "Move/Spread ratio:",
                round(ratio, 2)
            )

    print("\n" + "=" * 90)
    print("FULL DATA ANALYSIS FINISHED")
    print("=" * 90)


if __name__ == "__main__":
    main()
import csv
from collections import defaultdict
from datetime import datetime
from statistics import mean, median


FILE = "market_data_sample.csv"
HORIZON = 5


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
            t = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
            mid = float(row["mid"])
            spread = float(row["spread_pct"])

            data[symbol].append({
                "time": t,
                "mid": mid,
                "spread": spread
            })
        except Exception:
            continue

    print("=" * 75)
    print("MARKET DATA DIAGNOSTIC")
    print("File:", FILE)
    print("Total rows:", len(rows))
    print("Horizon:", HORIZON, "same-symbol observations")
    print("=" * 75)

    for symbol in sorted(data.keys()):
        items = data[symbol]

        if len(items) <= HORIZON:
            print("\n", symbol, "- NOT ENOUGH DATA")
            continue

        intervals = []
        spreads = []
        moves = []
        abs_moves = []
        max_favorable = []
        max_adverse = []

        for i in range(1, len(items)):
            dt = (items[i]["time"] - items[i - 1]["time"]).total_seconds()
            if dt > 0:
                intervals.append(dt)

        for i in range(len(items) - HORIZON):
            current = items[i]
            future = items[i + HORIZON]

            move = pct_change(current["mid"], future["mid"])

            spreads.append(current["spread"])
            moves.append(move)
            abs_moves.append(abs(move))

            if move > 0:
                max_favorable.append(move)
            else:
                max_adverse.append(move)

        print("\n" + "-" * 75)
        print("SYMBOL:", symbol)
        print("Rows:", len(items))

        if intervals:
            print("Avg interval (sec):",
                  round(mean(intervals), 2))
            print("Median interval (sec):",
                  round(median(intervals), 2))

        print("Avg spread (%):",
              round(mean(spreads), 4))

        print("Median spread (%):",
              round(median(spreads), 4))

        print("Avg 5-step move (%):",
              round(mean(moves), 4))

        print("Median 5-step move (%):",
              round(median(moves), 4))

        print("Avg absolute 5-step move (%):",
              round(mean(abs_moves), 4))

        print("Max favorable 5-step move (%):",
              round(max(moves), 4))

        print("Min 5-step move (%):",
              round(min(moves), 4))

        positive = sum(1 for x in moves if x > 0)
        negative = sum(1 for x in moves if x < 0)
        flat = sum(1 for x in moves if x == 0)

        total = len(moves)

        print("Positive moves (%):",
              round(positive / total * 100, 2))

        print("Negative moves (%):",
              round(negative / total * 100, 2))

        print("Flat moves (%):",
              round(flat / total * 100, 2))

    print("\n" + "=" * 75)
    print("DIAGNOSTIC FINISHED")
    print("=" * 75)


if __name__ == "__main__":
    main()
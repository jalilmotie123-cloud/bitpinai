# -*- coding: utf-8 -*-

import csv
from collections import defaultdict
from statistics import mean, median


FILE = "market_data_v2.csv"
HORIZONS = [5, 15, 30]


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
    w = pos - low

    return (
        values[low] * (1.0 - w)
        + values[high] * w
    )


def analyze_factor(name, records):

    if not records:
        print("\n", name)
        print("Signals: 0")
        return

    moves = [r["move"] for r in records]

    print("\n" + name)
    print("Signals:", len(records))

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
        round(
            sum(1 for x in moves if x > 0)
            / len(moves) * 100,
            2
        )
    )

    print(
        "Negative (%):",
        round(
            sum(1 for x in moves if x < 0)
            / len(moves) * 100,
            2
        )
    )

    print(
        "Avg spread (%):",
        round(
            mean(r["spread"] for r in records),
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
                "time": row["time"],
                "mid": float(row["mid"]),
                "spread": float(row["spread_pct"]),

                "obi1": float(row["obi1"]),
                "obi3": float(row["obi3"]),
                "obi5": float(row["obi5"]),
                "obi10": float(row["obi10"]),

                "ofi": float(row["ofi_norm"])
            })

        except Exception:
            continue

    print("=" * 95)
    print("BITPIN V2 FACTOR DIAGNOSTIC")
    print("File:", FILE)
    print("Rows:", len(rows))
    print("=" * 95)

    for symbol in sorted(data):

        items = data[symbol]

        print("\n" + "#" * 95)
        print("SYMBOL:", symbol)
        print("ROWS:", len(items))
        print("#" * 95)

        for horizon in HORIZONS:

            if len(items) <= horizon:
                continue

            observations = []

            for i in range(len(items) - horizon):

                future_move = pct_change(
                    items[i]["mid"],
                    items[i + horizon]["mid"]
                )

                observations.append({
                    "future_move": future_move,
                    "spread": items[i]["spread"],
                    "obi1": items[i]["obi1"],
                    "obi3": items[i]["obi3"],
                    "obi5": items[i]["obi5"],
                    "obi10": items[i]["obi10"],
                    "ofi": items[i]["ofi"]
                })

            print("\n" + "-" * 80)
            print("HORIZON:", horizon)
            print(
                "Approx observations:",
                len(observations)
            )

            # ------------------------------------------------
            # OBI10
            # ------------------------------------------------

            obi10_values = [
                r["obi10"]
                for r in observations
            ]

            obi10_low = percentile(
                obi10_values,
                0.10
            )

            obi10_high = percentile(
                obi10_values,
                0.90
            )

            obi_long = [
                {
                    "move": r["future_move"],
                    "spread": r["spread"]
                }
                for r in observations
                if r["obi10"] >= obi10_high
            ]

            obi_short = [
                {
                    "move": -r["future_move"],
                    "spread": r["spread"]
                }
                for r in observations
                if r["obi10"] <= obi10_low
            ]

            analyze_factor(
                "OBI10 TOP 10% LONG",
                obi_long
            )

            analyze_factor(
                "OBI10 BOTTOM 10% SHORT",
                obi_short
            )

            # ------------------------------------------------
            # OFI
            # ------------------------------------------------

            ofi_values = [
                r["ofi"]
                for r in observations
            ]

            ofi_low = percentile(
                ofi_values,
                0.10
            )

            ofi_high = percentile(
                ofi_values,
                0.90
            )

            ofi_long = [
                {
                    "move": r["future_move"],
                    "spread": r["spread"]
                }
                for r in observations
                if r["ofi"] >= ofi_high
            ]

            ofi_short = [
                {
                    "move": -r["future_move"],
                    "spread": r["spread"]
                }
                for r in observations
                if r["ofi"] <= ofi_low
            ]

            analyze_factor(
                "OFI TOP 10% LONG",
                ofi_long
            )

            analyze_factor(
                "OFI BOTTOM 10% SHORT",
                ofi_short
            )

            # ------------------------------------------------
            # ترکیب OBI10 + OFI
            # ------------------------------------------------

            combined = []

            for r in observations:
                score = r["obi10"] + r["ofi"]

                combined.append({
                    "score": score,
                    "move": r["future_move"],
                    "spread": r["spread"]
                })

            score_values = [
                r["score"]
                for r in combined
            ]

            score_low = percentile(
                score_values,
                0.10
            )

            score_high = percentile(
                score_values,
                0.90
            )

            combo_long = [
                {
                    "move": r["move"],
                    "spread": r["spread"]
                }
                for r in combined
                if r["score"] >= score_high
            ]

            combo_short = [
                {
                    "move": -r["move"],
                    "spread": r["spread"]
                }
                for r in combined
                if r["score"] <= score_low
            ]

            analyze_factor(
                "OBI10 + OFI TOP 10% LONG",
                combo_long
            )

            analyze_factor(
                "OBI10 + OFI BOTTOM 10% SHORT",
                combo_short
            )

    print("\n" + "=" * 95)
    print("V2 FACTOR DIAGNOSTIC FINISHED")
    print("=" * 95)


if __name__ == "__main__":
    main()
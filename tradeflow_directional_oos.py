import csv
import math
import statistics
from bisect import bisect_left

INPUT = "tradeflow_features_v3.csv"

FEATURES = (
    "cvd_rate_log_30s",
    "cvd_rate_log_60s",
    "cvd_rate_log_120s",
)

HORIZONS = (30, 60, 120, 300)

TRAIN_FRAC = 0.70
FEE_RT_PCT = 0.70
MAX_GAP_SEC = 300.0


def quantile(values, q):
    values = sorted(values)

    if not values:
        return 0.0

    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)

    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def load():
    rows = []

    with open(INPUT, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for x in reader:
            try:
                t = float(x["time"])
                p = float(x["price"])

                if not math.isfinite(t) or not math.isfinite(p):
                    continue

                if p <= 0:
                    continue

                rows.append(x)

            except Exception:
                continue

    rows.sort(key=lambda x: float(x["time"]))
    return rows


def future_return(times, prices, i, horizon):
    t0 = times[i]
    p0 = prices[i]

    target = t0 + horizon
    j = bisect_left(times, target, i + 1)

    if j >= len(times):
        return None

    actual_gap = times[j] - t0

    # Reject observations crossing a large missing-data gap.
    if actual_gap > horizon + MAX_GAP_SEC:
        return None

    if prices[j] <= 0:
        return None

    return (prices[j] / p0 - 1.0) * 100.0


def main():
    rows = load()

    if len(rows) < 300:
        print("TOO_FEW_ROWS")
        return

    times = [float(x["time"]) for x in rows]
    prices = [float(x["price"]) for x in rows]

    split = int(len(rows) * TRAIN_FRAC)

    print("TRADEFLOW DIRECTIONAL OOS")
    print("ROWS =", len(rows))
    print("TRAIN =", split)
    print("TEST =", len(rows) - split)
    print("FEE_RT_PCT =", FEE_RT_PCT)

    for feature in FEATURES:
        train_values = []

        for x in rows[:split]:
            try:
                v = float(x[feature])

                if math.isfinite(v):
                    train_values.append(v)

            except Exception:
                pass

        q1 = quantile(train_values, 0.25)
        q3 = quantile(train_values, 0.75)

        long_test = []
        short_test = []

        for i in range(split, len(rows)):
            try:
                v = float(rows[i][feature])

                if not math.isfinite(v):
                    continue

                if v >= q3:
                    long_test.append(i)

                elif v <= q1:
                    short_test.append(i)

            except Exception:
                continue

        print("\nFEATURE =", feature)
        print("TRAIN_Q1 =", q1)
        print("TRAIN_Q3 =", q3)
        print("LONG_SIGNALS =", len(long_test))
        print("SHORT_SIGNALS =", len(short_test))
        print("NO_TRADE_TEST =", (len(rows) - split) - len(long_test) - len(short_test))

        for direction, indices in (
            ("LONG", long_test),
            ("SHORT", short_test),
        ):
            print("\n", direction)

            for h in HORIZONS:
                returns = []

                for i in indices:
                    r = future_return(
                        times,
                        prices,
                        i,
                        h
                    )

                    if r is None:
                        continue

                    if direction == "SHORT":
                        r = -r

                    returns.append(r)

                if not returns:
                    print(" H%d n=0" % h)
                    continue

                mean_r = statistics.mean(returns)
                median_r = statistics.median(returns)

                win_rate = (
                    sum(x > 0 for x in returns)
                    / float(len(returns))
                    * 100.0
                )

                after_fee = mean_r - FEE_RT_PCT

                print(
                    " H%d n=%d mean=%+.5f%% median=%+.5f%% "
                    "win=%.1f%% after_fee_screen=%+.5f%%"
                    % (
                        h,
                        len(returns),
                        mean_r,
                        median_r,
                        win_rate,
                        after_fee,
                    )
                )

    print(
        "\nNOTE: exploratory OOS only. "
        "Returns use trade price, not executable bid/ask. "
        "No slippage and no overlap control."
    )


if __name__ == "__main__":
    main()
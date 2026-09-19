import csv
import io
import math
import statistics
from bisect import bisect_right, bisect_left
from datetime import datetime

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data_v2.csv"
SYMBOL = "SOL_USDT"

FEATURE = "cvd_rate_log_60s"
HORIZONS = (60, 120, 300)

TRAIN_FRAC = 0.70
FEE_SIDE = 0.0035

ALIGN_LIMITS = (5.0, 15.0, 30.0)
EXIT_MAX_DELAY = 60.0
MAX_GAP_SEC = 300.0


def quantile(values, q):
    values = sorted(values)

    if not values:
        return 0.0

    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)

    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def load_tradeflow():
    rows = []

    with open(
        TRADEFLOW_FILE,
        encoding="utf-8-sig",
        newline=""
    ) as f:
        reader = csv.DictReader(f)

        for x in reader:
            try:
                t = float(x["time"])
                p = float(x["price"])
                feature = float(x[FEATURE])

                if not (
                    math.isfinite(t)
                    and math.isfinite(p)
                    and math.isfinite(feature)
                ):
                    continue

                if p <= 0:
                    continue

                rows.append(x)

            except Exception:
                continue

    rows.sort(key=lambda x: float(x["time"]))
    return rows


def load_market():
    raw = open(MARKET_FILE, "rb").read()
    raw = raw.replace(b"\x00", b"")
    text = raw.decode("utf-8-sig")

    result = []

    reader = csv.DictReader(io.StringIO(text))

    for x in reader:
        if x.get("symbol") != SYMBOL:
            continue

        try:
            t = datetime.strptime(
                x["time"],
                "%Y-%m-%d %H:%M:%S.%f"
            ).timestamp()

            bid = float(x["bid"])
            ask = float(x["ask"])

            if (
                not math.isfinite(t)
                or not math.isfinite(bid)
                or not math.isfinite(ask)
            ):
                continue

            if bid <= 0 or ask <= 0 or ask < bid:
                continue

            result.append((t, bid, ask))

        except Exception:
            continue

    result.sort(key=lambda x: x[0])

    clean = []
    seen = set()

    for row in result:
        if row[0] in seen:
            continue

        seen.add(row[0])
        clean.append(row)

    return clean


def find_entry(market_times, market_bids, market_asks, signal_time, max_age):
    j = bisect_right(market_times, signal_time) - 1

    if j < 0:
        return None

    age = signal_time - market_times[j]

    if age < 0 or age > max_age:
        return None

    return {
        "index": j,
        "time": market_times[j],
        "bid": market_bids[j],
        "ask": market_asks[j],
        "age": age,
    }


def find_exit(
    market_times,
    market_bids,
    market_asks,
    entry_time,
    horizon
):
    target = entry_time + horizon

    j = bisect_left(market_times, target)

    if j >= len(market_times):
        return None

    delay = market_times[j] - target

    if delay > EXIT_MAX_DELAY:
        return None

    return {
        "index": j,
        "time": market_times[j],
        "bid": market_bids[j],
        "ask": market_asks[j],
        "delay": delay,
    }


def long_net_return(entry_ask, exit_bid):
    return (
        exit_bid * (1.0 - FEE_SIDE)
        / (entry_ask * (1.0 + FEE_SIDE))
        - 1.0
    ) * 100.0


def main():
    trades = load_tradeflow()
    market = load_market()

    print("TRADEFLOW ALIGNMENT OOS")
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))
    print("FEATURE =", FEATURE)
    print("SYMBOL =", SYMBOL)
    print("FEE_SIDE =", FEE_SIDE)

    if len(trades) < 300 or len(market) < 300:
        print("TOO_FEW_DATA")
        return

    market_times = [x[0] for x in market]
    market_bids = [x[1] for x in market]
    market_asks = [x[2] for x in market]

    split = int(len(trades) * TRAIN_FRAC)

    train_values = []

    for x in trades[:split]:
        try:
            v = float(x[FEATURE])

            if math.isfinite(v):
                train_values.append(v)

        except Exception:
            pass

    q3 = quantile(train_values, 0.75)

    print("TRAIN_ROWS =", split)
    print("TEST_ROWS =", len(trades) - split)
    print("TRAIN_Q3 =", q3)

    for align_limit in ALIGN_LIMITS:
        candidates = []

        for i in range(split, len(trades)):
            x = trades[i]

            try:
                feature_value = float(x[FEATURE])
                signal_time = float(x["time"])

                if not math.isfinite(feature_value):
                    continue

                # Long direction uses only the upper train quartile.
                if feature_value < q3:
                    continue

                entry = find_entry(
                    market_times,
                    market_bids,
                    market_asks,
                    signal_time,
                    align_limit
                )

                if entry is None:
                    continue

                candidates.append({
                    "entry_time": entry["time"],
                    "entry_bid": entry["bid"],
                    "entry_ask": entry["ask"],
                    "entry_age": entry["age"],
                })

            except Exception:
                continue

        print(
            "\nALIGN_LIMIT_SEC = %.0f LONG_CANDIDATES = %d"
            % (align_limit, len(candidates))
        )

        for horizon in HORIZONS:
            results = []
            last_exit = -1.0

            for c in candidates:
                if c["entry_time"] < last_exit:
                    continue

                exit_info = find_exit(
                    market_times,
                    market_bids,
                    market_asks,
                    c["entry_time"],
                    horizon
                )

                if exit_info is None:
                    continue

                net_r = long_net_return(
                    c["entry_ask"],
                    exit_info["bid"]
                )

                if not math.isfinite(net_r):
                    continue

                results.append(net_r)
                last_exit = exit_info["time"]

            if not results:
                print(" H%d n=0" % horizon)
                continue

            mean_r = statistics.mean(results)
            median_r = statistics.median(results)

            win_rate = (
                sum(x > 0 for x in results)
                / float(len(results))
                * 100.0
            )

            print(
                " H%d n=%d mean=%+.5f%% median=%+.5f%% "
                "win=%.1f%% total=%+.5f%%"
                % (
                    horizon,
                    len(results),
                    mean_r,
                    median_r,
                    win_rate,
                    sum(results),
                )
            )

    print(
        "\nNOTE: exploratory OOS only. "
        "Entry uses the latest market snapshot BEFORE the Trade Flow signal. "
        "Long entry = ASK and exit = BID. "
        "Two-sided fees included. "
        "No live trading."
    )


if __name__ == "__main__":
    main()
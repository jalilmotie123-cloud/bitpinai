import csv
import io
import math
import statistics
from bisect import bisect_right, bisect_left
from datetime import datetime

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data_v2.csv"
SYMBOL = "SOL_USDT"

CVD_FEATURE = "cvd_rate_log_60s"
INTENSITY_FEATURE = "intensity_60s"

HORIZONS = (300, 600, 1200)

TRAIN_FRAC = 0.70
FEE_SIDE = 0.0035

ALIGN_LIMIT_SEC = 30.0
EXIT_MAX_DELAY_SEC = 120.0


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
                cvd = float(x[CVD_FEATURE])
                intensity = float(x[INTENSITY_FEATURE])

                if not (
                    math.isfinite(t)
                    and math.isfinite(cvd)
                    and math.isfinite(intensity)
                ):
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

    rows = []

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

            rows.append((t, bid, ask))

        except Exception:
            continue

    rows.sort(key=lambda x: x[0])

    clean = []
    seen = set()

    for row in rows:
        if row[0] in seen:
            continue

        seen.add(row[0])
        clean.append(row)

    return clean


def find_entry(times, bids, asks, signal_time):
    j = bisect_right(times, signal_time) - 1

    if j < 0:
        return None

    age = signal_time - times[j]

    if age < 0 or age > ALIGN_LIMIT_SEC:
        return None

    return {
        "time": times[j],
        "bid": bids[j],
        "ask": asks[j],
        "age": age,
    }


def find_exit(times, bids, asks, entry_time, horizon):
    target = entry_time + horizon

    j = bisect_left(times, target)

    if j >= len(times):
        return None

    delay = times[j] - target

    if delay > EXIT_MAX_DELAY_SEC:
        return None

    return {
        "time": times[j],
        "bid": bids[j],
        "ask": asks[j],
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

    print("TRADEFLOW MULTIFACTOR LONG-HORIZON OOS")
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))
    print("SYMBOL =", SYMBOL)
    print("CVD_FEATURE =", CVD_FEATURE)
    print("INTENSITY_FEATURE =", INTENSITY_FEATURE)
    print("ENTRY = ASK")
    print("EXIT = BID")
    print("FEE_SIDE =", FEE_SIDE)
    print("ALIGN_LIMIT_SEC =", ALIGN_LIMIT_SEC)
    print("EXIT_MAX_DELAY_SEC =", EXIT_MAX_DELAY_SEC)
    print("NON_OVERLAPPING = 1")

    if len(trades) < 300 or len(market) < 300:
        print("TOO_FEW_DATA")
        return

    market_times = [x[0] for x in market]
    market_bids = [x[1] for x in market]
    market_asks = [x[2] for x in market]

    split = int(len(trades) * TRAIN_FRAC)

    cvd_train = []
    intensity_train = []

    for x in trades[:split]:
        try:
            cvd = float(x[CVD_FEATURE])
            intensity = float(x[INTENSITY_FEATURE])

            if math.isfinite(cvd) and math.isfinite(intensity):
                cvd_train.append(cvd)
                intensity_train.append(intensity)

        except Exception:
            continue

    if len(cvd_train) < 100:
        print("TRAIN_TOO_SMALL")
        return

    # Fixed train-only thresholds.
    cvd_q3 = quantile(cvd_train, 0.75)
    intensity_q3 = quantile(intensity_train, 0.75)

    print("TRAIN_ROWS =", split)
    print("TEST_ROWS =", len(trades) - split)
    print("TRAIN_CVD_Q3 =", cvd_q3)
    print("TRAIN_INTENSITY_Q3 =", intensity_q3)

    candidates = []

    for i in range(split, len(trades)):
        x = trades[i]

        try:
            signal_time = float(x["time"])
            cvd = float(x[CVD_FEATURE])
            intensity = float(x[INTENSITY_FEATURE])

            # Both factors must confirm.
            if cvd < cvd_q3:
                continue

            if intensity < intensity_q3:
                continue

            entry = find_entry(
                market_times,
                market_bids,
                market_asks,
                signal_time
            )

            if entry is None:
                continue

            candidates.append({
                "signal_time": signal_time,
                "entry_time": entry["time"],
                "entry_bid": entry["bid"],
                "entry_ask": entry["ask"],
                "entry_age": entry["age"],
            })

        except Exception:
            continue

    print("LONG_CANDIDATES =", len(candidates))

    for horizon in HORIZONS:
        results = []
        last_exit_time = -1.0

        for c in candidates:
            if c["entry_time"] < last_exit_time:
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

            results.append({
                "return": net_r,
                "entry_age": c["entry_age"],
                "exit_delay": exit_info["delay"],
            })

            last_exit_time = exit_info["time"]

        if not results:
            print(" H%d n=0" % horizon)
            continue

        returns = [x["return"] for x in results]

        mean_r = statistics.mean(returns)
        median_r = statistics.median(returns)

        win_rate = (
            sum(x > 0 for x in returns)
            / float(len(returns))
            * 100.0
        )

        avg_entry_age = statistics.mean(
            x["entry_age"] for x in results
        )

        avg_exit_delay = statistics.mean(
            x["exit_delay"] for x in results
        )

        print(
            " H%d n=%d mean=%+.5f%% median=%+.5f%% "
            "win=%.1f%% total=%+.5f%% "
            "avg_entry_age=%.2fs avg_exit_delay=%.2fs"
            % (
                horizon,
                len(returns),
                mean_r,
                median_r,
                win_rate,
                sum(returns),
                avg_entry_age,
                avg_exit_delay,
            )
        )

    print(
        "\nNOTE:"
        "\nBoth factors use TRAIN-only Q3 thresholds."
        "\nNo threshold tuning on TEST."
        "\nLong entry = ASK; exit = BID."
        "\nTwo-sided fees included."
        "\nNon-overlapping trades."
        "\nResearch only; no live trading."
    )


if __name__ == "__main__":
    main()
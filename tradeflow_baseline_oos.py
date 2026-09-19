import csv
import io
import math
import random
import statistics
from bisect import bisect_right, bisect_left
from datetime import datetime

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data_v2.csv"
SYMBOL = "SOL_USDT"

HORIZONS = (60, 120, 300)

TRAIN_FRAC = 0.70
FEE_SIDE = 0.0035

ALIGN_LIMIT_SEC = 30.0
EXIT_MAX_DELAY_SEC = 60.0

REPEATS = 50
SEED = 20260918


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

                if not math.isfinite(t):
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


def find_entry(market_times, market_bids, market_asks, signal_time):
    j = bisect_right(market_times, signal_time) - 1

    if j < 0:
        return None

    age = signal_time - market_times[j]

    if age < 0 or age > ALIGN_LIMIT_SEC:
        return None

    return (
        market_times[j],
        market_bids[j],
        market_asks[j]
    )


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

    if delay > EXIT_MAX_DELAY_SEC:
        return None

    return (
        market_times[j],
        market_bids[j],
        market_asks[j]
    )


def long_net_return(entry_ask, exit_bid):
    return (
        exit_bid * (1.0 - FEE_SIDE)
        / (entry_ask * (1.0 + FEE_SIDE))
        - 1.0
    ) * 100.0


def make_eligible_entries(trades, split, market_times, market_bids, market_asks):
    entries = []

    for i in range(split, len(trades)):
        try:
            signal_time = float(trades[i]["time"])

            entry = find_entry(
                market_times,
                market_bids,
                market_asks,
                signal_time
            )

            if entry is None:
                continue

            entries.append({
                "entry_time": entry[0],
                "entry_bid": entry[1],
                "entry_ask": entry[2],
            })

        except Exception:
            continue

    return entries


def run_sample(entries, horizon, sample_size, rng,
               market_times, market_bids, market_asks):

    if len(entries) <= sample_size:
        chosen = list(entries)
    else:
        chosen = rng.sample(entries, sample_size)

    chosen.sort(key=lambda x: x["entry_time"])

    results = []
    last_exit = -1.0

    for c in chosen:
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
            exit_info[1]
        )

        if not math.isfinite(net_r):
            continue

        results.append(net_r)
        last_exit = exit_info[0]

    return results


def main():
    trades = load_tradeflow()
    market = load_market()

    print("TRADEFLOW BASELINE / PLACEBO OOS")
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))
    print("SYMBOL =", SYMBOL)
    print("ENTRY = ASK")
    print("EXIT = BID")
    print("FEE_SIDE =", FEE_SIDE)
    print("ALIGN_LIMIT_SEC =", ALIGN_LIMIT_SEC)
    print("NON_OVERLAPPING = 1")
    print("REPEATS =", REPEATS)
    print("SEED =", SEED)

    if len(trades) < 300 or len(market) < 300:
        print("TOO_FEW_DATA")
        return

    market_times = [x[0] for x in market]
    market_bids = [x[1] for x in market]
    market_asks = [x[2] for x in market]

    split = int(len(trades) * TRAIN_FRAC)

    eligible = make_eligible_entries(
        trades,
        split,
        market_times,
        market_bids,
        market_asks
    )

    print("TRAIN_ROWS =", split)
    print("TEST_ROWS =", len(trades) - split)
    print("ELIGIBLE_ENTRY_TIMES =", len(eligible))

    # Signal counts from the previously tested multifactor setup.
    # These are fixed observations, not optimized here.
    target_sizes = {
        60: 19,
        120: 16,
        300: 12,
    }

    rng = random.Random(SEED)

    for horizon in HORIZONS:
        target = target_sizes[horizon]

        all_means = []
        all_medians = []
        all_wins = []
        all_ns = []

        for _ in range(REPEATS):
            results = run_sample(
                eligible,
                horizon,
                target,
                rng,
                market_times,
                market_bids,
                market_asks
            )

            if not results:
                continue

            all_means.append(statistics.mean(results))
            all_medians.append(statistics.median(results))

            all_wins.append(
                sum(x > 0 for x in results)
                / float(len(results))
                * 100.0
            )

            all_ns.append(len(results))

        if not all_means:
            print("H%d NO_VALID_BASELINE" % horizon)
            continue

        mean_of_means = statistics.mean(all_means)
        p10 = sorted(all_means)[int(0.10 * (len(all_means) - 1))]
        p50 = statistics.median(all_means)
        p90 = sorted(all_means)[int(0.90 * (len(all_means) - 1))]

        print(
            "\nH%d"
            "\n TARGET_SAMPLE=%d"
            "\n REPEATS=%d"
            "\n AVG_TRADE_COUNT=%.2f"
            "\n BASELINE_MEAN_OF_MEANS=%+.5f%%"
            "\n BASELINE_MEAN_P10=%+.5f%%"
            "\n BASELINE_MEAN_MEDIAN=%+.5f%%"
            "\n BASELINE_MEAN_P90=%+.5f%%"
            "\n AVG_WIN_RATE=%.1f%%"
            % (
                horizon,
                target,
                len(all_means),
                statistics.mean(all_ns),
                mean_of_means,
                p10,
                p50,
                p90,
                statistics.mean(all_wins),
            )
        )

    print(
        "\nNOTE:"
        "\nThis is a placebo baseline using random eligible test times."
        "\nSample sizes are matched approximately to the previously tested multifactor result."
        "\nExecution uses ASK entry / BID exit with two-sided fees."
        "\nThis is diagnostic only; it does not validate a trading strategy."
    )


if __name__ == "__main__":
    main()
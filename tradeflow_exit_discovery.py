import csv
import io
import math
import statistics
from bisect import bisect_right
from datetime import datetime

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data.csv"
SYMBOL = "SOL_USDT"

CVD_FEATURE = "cvd_rate_log_60s"
INTENSITY_FEATURE = "intensity_60s"

FEE_SIDE = 0.0035

N_FOLDS = 6
INITIAL_TRAIN_FRAC = 0.40

PURGE_SEC = 1200.0
EMBARGO_SEC = 1200.0
ALIGN_LIMIT_SEC = 30.0

HORIZONS = (300, 900, 1800, 3600)

TPS = (0.003, 0.005, 0.008, 0.010)
SLS = (0.002, 0.003, 0.005)


def quantile(values, q):
    values = sorted(values)

    if not values:
        return 0.0

    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)

    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def parse_time(value):
    value = str(value).strip()

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt).timestamp()
        except ValueError:
            pass

    raise ValueError("BAD_TIME")


def load_tradeflow():
    rows = []
    seen = set()

    with open(TRADEFLOW_FILE, encoding="utf-8-sig", newline="") as f:
        for x in csv.DictReader(f):

            trade_id = str(x.get("id", "")).strip()

            if not trade_id or trade_id in seen:
                continue

            try:
                t = float(x["time"])
                cvd = float(x[CVD_FEATURE])
                intensity = float(x[INTENSITY_FEATURE])

                if not all(
                    math.isfinite(v)
                    for v in (t, cvd, intensity)
                ):
                    continue

                seen.add(trade_id)

                rows.append({
                    "id": trade_id,
                    "time": t,
                    "cvd": cvd,
                    "intensity": intensity,
                })

            except Exception:
                continue

    rows.sort(key=lambda x: x["time"])
    return rows


def load_market():
    raw = open(MARKET_FILE, "rb").read()
    raw = raw.replace(b"\x00", b"")
    text = raw.decode("utf-8-sig")

    rows = []

    for x in csv.DictReader(io.StringIO(text)):

        if x.get("symbol") != SYMBOL:
            continue

        try:
            t = parse_time(x["time"])
            bid = float(x["bid"])
            ask = float(x["ask"])

            if not all(
                math.isfinite(v)
                for v in (t, bid, ask)
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
        "index": j,
        "time": times[j],
        "bid": bids[j],
        "ask": asks[j],
        "age": age,
    }


def evaluate_long(
    entry_price,
    start_index,
    times,
    bids,
    asks,
    horizon,
    tp,
    sl
):
    end_time = times[start_index] + horizon
    end_index = bisect_right(times, end_time) - 1

    if end_index <= start_index:
        return None

    tp_price = entry_price * (1.0 + tp)
    sl_price = entry_price * (1.0 - sl)

    for j in range(start_index + 1, end_index + 1):

        exit_price = bids[j]

        if exit_price >= tp_price:
            return "TP", exit_price, times[j]

        if exit_price <= sl_price:
            return "SL", exit_price, times[j]

    return "TIME", bids[end_index], times[end_index]


def evaluate_short(
    entry_price,
    start_index,
    times,
    bids,
    asks,
    horizon,
    tp,
    sl
):
    end_time = times[start_index] + horizon
    end_index = bisect_right(times, end_time) - 1

    if end_index <= start_index:
        return None

    tp_price = entry_price * (1.0 - tp)
    sl_price = entry_price * (1.0 + sl)

    for j in range(start_index + 1, end_index + 1):

        exit_price = asks[j]

        if exit_price <= tp_price:
            return "TP", exit_price, times[j]

        if exit_price >= sl_price:
            return "SL", exit_price, times[j]

    return "TIME", asks[end_index], times[end_index]


def long_return(entry, exit_price):
    return (
        exit_price * (1.0 - FEE_SIDE)
        / (entry * (1.0 + FEE_SIDE))
        - 1.0
    ) * 100.0


def short_return(entry, exit_price):
    return (
        entry * (1.0 - FEE_SIDE)
        / (exit_price * (1.0 + FEE_SIDE))
        - 1.0
    ) * 100.0


def main():

    trades = load_tradeflow()
    market = load_market()

    print("TRADEFLOW EXIT DISCOVERY")
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))
    print("SYMBOL =", SYMBOL)
    print("ENTRY SIGNAL = CVD60 Q3 + INTENSITY60 Q3")
    print("EXECUTION = TAKER ASK/BID")
    print("FEE_SIDE =", FEE_SIDE)
    print("HORIZONS =", HORIZONS)
    print("TP =", TPS)
    print("SL =", SLS)
    print("N_FOLDS =", N_FOLDS)
    print("PURGE_SEC =", PURGE_SEC)
    print("EMBARGO_SEC =", EMBARGO_SEC)
    print("NON_OVERLAPPING = 1")
    print("")

    if len(trades) < 1000 or len(market) < 1000:
        print("TOO_FEW_DATA")
        return

    mt = [x[0] for x in market]
    mb = [x[1] for x in market]
    ma = [x[2] for x in market]

    n = len(trades)

    initial_train = int(n * INITIAL_TRAIN_FRAC)
    remaining = n - initial_train
    fold_size = remaining // N_FOLDS

    aggregate = {}

    for tp in TPS:
        for sl in SLS:
            for h in HORIZONS:

                aggregate[(tp, sl, h, "LONG")] = []
                aggregate[(tp, sl, h, "SHORT")] = []

    for fold in range(N_FOLDS):

        raw_start = initial_train + fold * fold_size

        if fold == N_FOLDS - 1:
            raw_end = n
        else:
            raw_end = initial_train + (fold + 1) * fold_size

        test_start_time = trades[raw_start]["time"]

        train_end_time = test_start_time - PURGE_SEC
        eval_start_time = test_start_time + EMBARGO_SEC

        train = [
            x for x in trades
            if x["time"] < train_end_time
        ]

        test = [
            x for x in trades[raw_start:raw_end]
            if x["time"] >= eval_start_time
        ]

        cvd_train = [x["cvd"] for x in train]
        intensity_train = [x["intensity"] for x in train]

        if not cvd_train or not intensity_train:
            print("FOLD", fold + 1, "TRAIN_TOO_SMALL")
            continue

        cvd_q3 = quantile(cvd_train, 0.75)
        intensity_q3 = quantile(intensity_train, 0.75)

        candidates = []

        for x in test:

            if x["cvd"] < cvd_q3:
                continue

            if x["intensity"] < intensity_q3:
                continue

            entry = find_entry(
                mt,
                mb,
                ma,
                x["time"]
            )

            if entry is None:
                continue

            candidates.append(entry)

        print(
            "FOLD",
            fold + 1,
            "| TRAIN=",
            len(train),
            "| TEST=",
            len(test),
            "| CANDIDATES=",
            len(candidates)
        )

        for tp in TPS:
            for sl in SLS:
                for h in HORIZONS:

                    for direction in ("LONG", "SHORT"):

                        values = []
                        used_until = -1.0

                        for c in candidates:

                            if c["time"] <= used_until:
                                continue

                            if direction == "LONG":
                                result = evaluate_long(
                                    c["ask"],
                                    c["index"],
                                    mt,
                                    mb,
                                    ma,
                                    h,
                                    tp,
                                    sl
                                )
                            else:
                                result = evaluate_short(
                                    c["bid"],
                                    c["index"],
                                    mt,
                                    mb,
                                    ma,
                                    h,
                                    tp,
                                    sl
                                )

                            if result is None:
                                continue

                            kind, exit_price, exit_time = result

                            if direction == "LONG":
                                r = long_return(
                                    c["ask"],
                                    exit_price
                                )
                            else:
                                r = short_return(
                                    c["bid"],
                                    exit_price
                                )

                            values.append(r)
                            used_until = exit_time

                        aggregate[
                            (tp, sl, h, direction)
                        ].extend(values)

    print("")
    print("========================================")
    print("EXIT DISCOVERY SUMMARY")
    print("========================================")

    for direction in ("LONG", "SHORT"):

        print("")
        print("DIRECTION =", direction)

        for h in HORIZONS:

            print("")
            print("HORIZON =", h)

            for tp in TPS:

                for sl in SLS:

                    values = aggregate[
                        (tp, sl, h, direction)
                    ]

                    if not values:
                        print(
                            "TP=%.3f SL=%.3f N=0"
                            % (tp, sl)
                        )
                        continue

                    mean = statistics.mean(values)
                    median = statistics.median(values)

                    win = (
                        sum(x > 0 for x in values)
                        / len(values)
                        * 100.0
                    )

                    total = sum(values)

                    print(
                        "TP=%.3f SL=%.3f | N=%d | "
                        "MEAN=%.5f%% | MEDIAN=%.5f%% | "
                        "WIN=%.1f%% | SUM=%.5f%%"
                        % (
                            tp,
                            sl,
                            len(values),
                            mean,
                            median,
                            win,
                            total
                        )
                    )

    print("")
    print("IMPORTANT")
    print("This is an exploratory exit-grid test.")
    print("No TP/SL is approved from this test alone.")
    print("Execution uses TAKER ASK/BID, not maker fill assumptions.")
    print("STATUS = EXIT_DISCOVERY_ONLY")


if __name__ == "__main__":
    main()
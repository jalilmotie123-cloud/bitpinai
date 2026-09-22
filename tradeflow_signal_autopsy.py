import csv
import io
import math
import statistics
from bisect import bisect_right, bisect_left
from datetime import datetime

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data.csv"
SYMBOL = "SOL_USDT"

CVD = "cvd_rate_log_60s"
INTENSITY = "intensity_60s"
PRE_PRICE = "price_change_60s_pct"

TRAIN_FRAC = 0.70
Q = 0.75
FEE_SIDE = 0.0035
ALIGN_LIMIT_SEC = 30.0
EXIT_MAX_DELAY_SEC = 120.0

HORIZONS = (300, 600, 1200)


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
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
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
                cvd = float(x[CVD])
                intensity = float(x[INTENSITY])
                pre_price = float(x[PRE_PRICE])

                if not all(
                    math.isfinite(v)
                    for v in (t, cvd, intensity, pre_price)
                ):
                    continue

                seen.add(trade_id)
                rows.append({
                    "id": trade_id,
                    "time": t,
                    "cvd": cvd,
                    "intensity": intensity,
                    "pre_price": pre_price,
                })
            except Exception:
                continue

    rows.sort(key=lambda x: x["time"])
    return rows


def load_market():
    raw = open(MARKET_FILE, "rb").read().replace(b"\x00", b"")
    text = raw.decode("utf-8-sig")
    rows = []

    for x in csv.DictReader(io.StringIO(text)):
        if x.get("symbol") != SYMBOL:
            continue

        try:
            t = parse_time(x["time"])
            bid = float(x["bid"])
            ask = float(x["ask"])

            if not all(math.isfinite(v) for v in (t, bid, ask)):
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

    return times[j], bids[j], asks[j], age


def find_exit(times, bids, asks, entry_time, horizon):
    target = entry_time + horizon
    j = bisect_left(times, target)

    if j >= len(times):
        return None

    delay = times[j] - target
    if delay > EXIT_MAX_DELAY_SEC:
        return None

    return times[j], bids[j], asks[j], delay


def net_return(entry_ask, exit_bid):
    return (
        exit_bid * (1.0 - FEE_SIDE)
        / (entry_ask * (1.0 + FEE_SIDE))
        - 1.0
    ) * 100.0


def report(name, values):
    if not values:
        print(name, "N=0")
        return

    print(
        name,
        "N=", len(values),
        "MEAN=", round(statistics.mean(values), 5),
        "MEDIAN=", round(statistics.median(values), 5),
        "WIN=", round(
            sum(v > 0 for v in values) / len(values) * 100.0, 2
        ),
        "MIN=", round(min(values), 5),
        "MAX=", round(max(values), 5),
    )


def main():
    trades = load_tradeflow()
    market = load_market()

    print("TRADEFLOW SIGNAL AUTOPSY")
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))
    print("SYMBOL =", SYMBOL)
    print("CVD =", CVD)
    print("INTENSITY =", INTENSITY)
    print("ENTRY = ASK")
    print("EXIT = BID")
    print("FEE_SIDE =", FEE_SIDE)
    print("ALIGN_LIMIT_SEC =", ALIGN_LIMIT_SEC)
    print("")

    if len(trades) < 1000 or len(market) < 1000:
        print("TOO_FEW_DATA")
        return

    split = int(len(trades) * TRAIN_FRAC)

    cvd_train = [x["cvd"] for x in trades[:split]]
    intensity_train = [x["intensity"] for x in trades[:split]]

    cvd_q3 = quantile(cvd_train, Q)
    intensity_q3 = quantile(intensity_train, Q)

    print("TRAIN_ROWS =", split)
    print("TEST_ROWS =", len(trades) - split)
    print("TRAIN_CVD_Q3 =", cvd_q3)
    print("TRAIN_INTENSITY_Q3 =", intensity_q3)

    times = [x[0] for x in market]
    bids = [x[1] for x in market]
    asks = [x[2] for x in market]

    candidates = []

    for x in trades[split:]:
        if x["cvd"] < cvd_q3:
            continue
        if x["intensity"] < intensity_q3:
            continue

        entry = find_entry(
            times,
            bids,
            asks,
            x["time"]
        )

        if entry is None:
            continue

        et, ebid, eask, age = entry

        candidates.append({
            "id": x["id"],
            "signal_time": x["time"],
            "entry_time": et,
            "entry_bid": ebid,
            "entry_ask": eask,
            "entry_age": age,
            "cvd": x["cvd"],
            "intensity": x["intensity"],
            "pre_price": x["pre_price"],
        })

    print("ALIGNED_CANDIDATES =", len(candidates))
    print("")

    if not candidates:
        print("NO_ALIGNED_CANDIDATES")
        return

    pre = [x["pre_price"] for x in candidates]
    cvds = [x["cvd"] for x in candidates]
    ints = [x["intensity"] for x in candidates]
    ages = [x["entry_age"] for x in candidates]

    report("PRE_PRICE_CHANGE_60S", pre)
    report("CVD_AT_SIGNAL", cvds)
    report("INTENSITY_AT_SIGNAL", ints)
    report("ENTRY_AGE_SEC", ages)

    print("")
    print("PRE_SIGNAL_DIRECTION")

    up = [x["pre_price"] for x in candidates if x["pre_price"] > 0]
    down = [x["pre_price"] for x in candidates if x["pre_price"] < 0]
    flat = [x["pre_price"] for x in candidates if x["pre_price"] == 0]

    print("ALREADY_UP =", len(up))
    print("ALREADY_DOWN =", len(down))
    print("FLAT =", len(flat))

    report("ALREADY_UP_PRE_MOVE", up)
    report("ALREADY_DOWN_PRE_MOVE", down)

    print("")
    print("EXECUTABLE RESULTS WITHOUT NON-OVERLAP")

    for horizon in HORIZONS:
        values = []
        raw_moves = []

        for c in candidates:
            ex = find_exit(
                times,
                bids,
                asks,
                c["entry_time"],
                horizon
            )

            if ex is None:
                continue

            exit_time, exit_bid, exit_ask, delay = ex

            values.append(
                net_return(c["entry_ask"], exit_bid)
            )

            raw_moves.append(
                (exit_bid / c["entry_ask"] - 1.0) * 100.0
            )

        print("")
        print("HORIZON =", horizon)
        report("NET_RETURN", values)
        report("RAW_ASK_TO_BID_MOVE", raw_moves)

    print("")
    print("EXECUTABLE RESULTS SPLIT BY PRE-60S PRICE DIRECTION")

    for horizon in HORIZONS:
        groups = {
            "UP": [],
            "DOWN": [],
            "FLAT": [],
        }

        for c in candidates:
            ex = find_exit(
                times,
                bids,
                asks,
                c["entry_time"],
                horizon
            )

            if ex is None:
                continue

            exit_bid = ex[1]
            r = net_return(c["entry_ask"], exit_bid)

            if c["pre_price"] > 0:
                groups["UP"].append(r)
            elif c["pre_price"] < 0:
                groups["DOWN"].append(r)
            else:
                groups["FLAT"].append(r)

        print("")
        print("HORIZON =", horizon)
        report("UP", groups["UP"])
        report("DOWN", groups["DOWN"])
        report("FLAT", groups["FLAT"])

    print("")
    print("STATUS = AUTOPSY_ONLY")
    print("NO_THRESHOLD_TUNING")
    print("NO_LIVE_TRADING")


if __name__ == "__main__":
    main()
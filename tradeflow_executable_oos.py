import csv
import io
import math
import statistics
from bisect import bisect_left, bisect_right

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data_v2.csv"
SYMBOL = "SOL_USDT"

FEATURES = (
    "cvd_rate_log_30s",
    "cvd_rate_log_60s",
    "cvd_rate_log_120s",
)

HORIZONS = (60, 120, 300)

TRAIN_FRAC = 0.70

FEE_SIDE = 0.0035

# Maximum age allowed for the market snapshot used as entry.
MAX_ENTRY_STALE_SEC = 60.0

# Maximum delay allowed after the target horizon for the exit snapshot.
MAX_EXIT_DELAY_SEC = 60.0

# Minimum trade count for a feature row to be considered.
MIN_TRADES = 5


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
                price = float(x["price"])

                if not math.isfinite(t):
                    continue

                if not math.isfinite(price) or price <= 0:
                    continue

                rows.append(x)

            except Exception:
                continue

    rows.sort(key=lambda x: float(x["time"]))
    return rows


def load_market():
    # Scanner may be writing the file while we read it.
    # Remove NUL bytes from the in-memory copy only.
    raw = open(MARKET_FILE, "rb").read()
    raw = raw.replace(b"\x00", b"")

    text = raw.decode("utf-8-sig")

    rows = []

    reader = csv.DictReader(io.StringIO(text))

    for x in reader:
        try:
            if x.get("symbol") != SYMBOL:
                continue

            t = x.get("time", "")

            if not t:
                continue

            # Market timestamps are formatted:
            # YYYY-MM-DD HH:MM:SS.fff
            from datetime import datetime

            ts = datetime.strptime(
                t,
                "%Y-%m-%d %H:%M:%S.%f"
            ).timestamp()

            bid = float(x["bid"])
            ask = float(x["ask"])

            if (
                not math.isfinite(ts)
                or not math.isfinite(bid)
                or not math.isfinite(ask)
            ):
                continue

            if bid <= 0 or ask <= 0 or ask < bid:
                continue

            rows.append((ts, bid, ask))

        except Exception:
            continue

    rows.sort(key=lambda x: x[0])

    # Remove exact timestamp duplicates.
    clean = []
    seen = set()

    for row in rows:
        if row[0] in seen:
            continue

        seen.add(row[0])
        clean.append(row)

    return clean


def execution_prices(market):
    times = [x[0] for x in market]
    bids = [x[1] for x in market]
    asks = [x[2] for x in market]

    return times, bids, asks


def find_entry(times, bids, asks, t_signal):
    j = bisect_right(times, t_signal) - 1

    if j < 0:
        return None

    stale = t_signal - times[j]

    if stale < 0 or stale > MAX_ENTRY_STALE_SEC:
        return None

    # LONG entry = ASK
    return {
        "index": j,
        "time": times[j],
        "bid": bids[j],
        "ask": asks[j],
        "stale": stale,
    }


def find_exit(times, bids, asks, entry_time, horizon):
    target = entry_time + horizon

    j = bisect_left(times, target)

    if j >= len(times):
        return None

    delay = times[j] - target

    if delay > MAX_EXIT_DELAY_SEC:
        return None

    return {
        "index": j,
        "time": times[j],
        "bid": bids[j],
        "ask": asks[j],
        "delay": delay,
    }


def long_net_return(entry_ask, exit_bid):
    # Exact two-sided percentage model for a long:
    #
    # Buy notional includes entry fee.
    # Sale proceeds are reduced by exit fee.
    #
    # This is more accurate than simply subtracting 0.70 points.
    return (
        exit_bid * (1.0 - FEE_SIDE)
        / (entry_ask * (1.0 + FEE_SIDE))
        - 1.0
    ) * 100.0


def main():
    trades = load_tradeflow()
    market = load_market()

    print("TRADEFLOW EXECUTABLE OOS")
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))
    print("SYMBOL =", SYMBOL)
    print("FEE_SIDE =", FEE_SIDE)
    print("ENTRY = ASK")
    print("EXIT = BID")
    print("NON_OVERLAPPING = 1")

    if len(trades) < 300:
        print("TOO_FEW_TRADEFLOW_ROWS")
        return

    if len(market) < 300:
        print("TOO_FEW_MARKET_ROWS")
        return

    market_times, market_bids, market_asks = execution_prices(market)

    split = int(len(trades) * TRAIN_FRAC)

    print("TRAIN_ROWS =", split)
    print("TEST_ROWS =", len(trades) - split)

    for feature in FEATURES:
        train_values = []

        for x in trades[:split]:
            try:
                v = float(x[feature])

                if math.isfinite(v):
                    train_values.append(v)

            except Exception:
                pass

        if len(train_values) < 100:
            print("\nFEATURE", feature, "SKIPPED_TRAIN_TOO_SMALL")
            continue

        q1 = quantile(train_values, 0.25)
        q3 = quantile(train_values, 0.75)

        print("\nFEATURE =", feature)
        print("TRAIN_Q1 =", q1)
        print("TRAIN_Q3 =", q3)

        # Long signal only.
        # A bearish/short interpretation is deliberately NOT treated
        # as an executable spot short until exchange short mechanics
        # are separately verified.
        candidates = []

        for i in range(split, len(trades)):
            x = trades[i]

            try:
                v = float(x[feature])
                t = float(x["time"])

                if not math.isfinite(v):
                    continue

                if v < q3:
                    continue

                entry = find_entry(
                    market_times,
                    market_bids,
                    market_asks,
                    t
                )

                if entry is None:
                    continue

                candidates.append(
                    {
                        "trade_index": i,
                        "signal_time": t,
                        "entry_time": entry["time"],
                        "entry_ask": entry["ask"],
                        "entry_bid": entry["bid"],
                        "entry_stale": entry["stale"],
                    }
                )

            except Exception:
                continue

        print("LONG_CANDIDATES =", len(candidates))

        for horizon in HORIZONS:
            results = []

            last_exit_time = -1.0

            for c in candidates:
                entry_time = c["entry_time"]

                # Non-overlapping trades.
                if entry_time < last_exit_time:
                    continue

                exit_info = find_exit(
                    market_times,
                    market_bids,
                    market_asks,
                    entry_time,
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

                results.append(
                    {
                        "return": net_r,
                        "entry_spread_pct": (
                            (c["entry_ask"] / c["entry_bid"] - 1.0)
                            * 100.0
                            if c["entry_bid"] > 0
                            else 0.0
                        ),
                        "entry_stale": c["entry_stale"],
                        "exit_delay": exit_info["delay"],
                    }
                )

                last_exit_time = exit_info["time"]

            if not results:
                print(
                    " H%d n=0" % horizon
                )
                continue

            returns = [x["return"] for x in results]

            mean_r = statistics.mean(returns)
            median_r = statistics.median(returns)

            win_rate = (
                sum(x > 0 for x in returns)
                / float(len(returns))
                * 100.0
            )

            total_net = sum(returns)

            avg_spread = statistics.mean(
                x["entry_spread_pct"]
                for x in results
            )

            avg_stale = statistics.mean(
                x["entry_stale"]
                for x in results
            )

            avg_exit_delay = statistics.mean(
                x["exit_delay"]
                for x in results
            )

            print(
                " H%d n=%d mean=%+.5f%% median=%+.5f%% "
                "win=%.1f%% total=%+.5f%% "
                "avg_entry_spread=%.5f%% "
                "avg_stale=%.2fs avg_exit_delay=%.2fs"
                % (
                    horizon,
                    len(returns),
                    mean_r,
                    median_r,
                    win_rate,
                    total_net,
                    avg_spread,
                    avg_stale,
                    avg_exit_delay,
                )
            )

    print(
        "\nNOTE:"
        "\nOOS thresholds come only from TRAIN."
        "\nLong execution = ASK entry / BID exit."
        "\nTwo-sided fee is applied explicitly."
        "\nTrades are non-overlapping."
        "\nThis is still research, not live trading."
    )


if __name__ == "__main__":
    main()
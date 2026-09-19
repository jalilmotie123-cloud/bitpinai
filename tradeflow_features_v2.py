import csv
import math
from collections import deque

INPUT = "matches_clean.csv"
OUTPUT = "tradeflow_features_v2.csv"

WINDOWS = (30, 60, 120)
GAP_SEC = 300.0

# Minimum number of trades required for a window to be considered reliable.
MIN_TRADES = 5

# Historical trade-size lookback for distribution-relative large-trade detection.
LARGE_LOOKBACK = 300
LARGE_Q = 0.95


def quantile(values, q):
    if not values:
        return 0.0

    values = sorted(values)
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)

    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def load_data():
    rows = []
    seen = set()

    with open(INPUT, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for x in reader:
            mid = str(x.get("id", "")).strip()

            if not mid or mid in seen:
                continue

            try:
                t = float(x["time"])
                price = float(x["price"])
                base = float(x["base_amount"])
                quote = float(x["quote_amount"])
                side = x["side"].strip().lower()

                if not (
                    math.isfinite(t)
                    and math.isfinite(price)
                    and math.isfinite(base)
                    and math.isfinite(quote)
                ):
                    continue

                if price <= 0 or base <= 0 or quote < 0:
                    continue

                if side not in ("buy", "sell"):
                    continue

                seen.add(mid)

                rows.append(
                    {
                        "id": mid,
                        "time": t,
                        "price": price,
                        "base_amount": base,
                        "quote_amount": quote,
                        "side": side,
                    }
                )

            except Exception:
                continue

    rows.sort(key=lambda x: x["time"])
    return rows


def main():
    data = load_data()

    if not data:
        print("NO_VALID_DATA")
        return

    windows = {}
    for w in WINDOWS:
        windows[w] = deque()

    # Previous trade sizes only.
    historical_sizes = deque(maxlen=LARGE_LOOKBACK)

    output_rows = []

    cumulative_cvd = 0.0
    previous_time = None

    for row in data:
        t = row["time"]
        q = row["quote_amount"]

        signed_volume = q if row["side"] == "buy" else -q

        # Start a new independent segment after a long data gap.
        if previous_time is not None and t - previous_time > GAP_SEC:
            for w in WINDOWS:
                windows[w].clear()

            historical_sizes.clear()
            cumulative_cvd = 0.0

        cumulative_cvd += signed_volume

        out = {
            "id": row["id"],
            "time": row["time"],
            "price": row["price"],
            "base_amount": row["base_amount"],
            "quote_amount": row["quote_amount"],
            "side": row["side"],
            "signed_volume": signed_volume,
            "cvd": cumulative_cvd,
        }

        # IMPORTANT:
        # Large-trade threshold uses ONLY PREVIOUS trades.
        # This avoids using the current trade to define its own threshold.
        previous_p95 = quantile(
            list(historical_sizes),
            LARGE_Q
        ) if historical_sizes else 0.0

        if previous_p95 > 0 and q >= previous_p95:
            out["large_trade"] = 1
        else:
            out["large_trade"] = 0

        for w in WINDOWS:
            dq = windows[w]

            dq.append(
                (
                    t,
                    q,
                    signed_volume,
                    row["side"],
                    row["price"],
                )
            )

            while dq and t - dq[0][0] > w:
                dq.popleft()

            count = len(dq)

            buy_count = sum(1 for x in dq if x[3] == "buy")
            sell_count = sum(1 for x in dq if x[3] == "sell")

            buy_volume = sum(x[1] for x in dq if x[3] == "buy")
            sell_volume = sum(x[1] for x in dq if x[3] == "sell")

            total_volume = buy_volume + sell_volume
            delta = buy_volume - sell_volume

            eligible = 1 if count >= MIN_TRADES else 0

            if total_volume > 0:
                delta_ratio = delta / total_volume
            else:
                delta_ratio = 0.0

            if count > 0:
                count_imbalance = (
                    float(buy_count - sell_count) / float(count)
                )
            else:
                count_imbalance = 0.0

            intensity = float(count) / float(w)

            if previous_p95 > 0 and total_volume > 0:
                large_volume = sum(
                    x[1] for x in dq if x[1] >= previous_p95
                )
                large_ratio = large_volume / total_volume
            else:
                large_ratio = 0.0

            if dq:
                first_time = dq[0][0]
                first_price = dq[0][4]

                elapsed = max(t - first_time, 0.001)

                price_change_pct = (
                    (row["price"] / first_price - 1.0) * 100.0
                    if first_price > 0 else 0.0
                )

                cvd_change = sum(x[2] for x in dq)
                cvd_slope = cvd_change / elapsed
            else:
                price_change_pct = 0.0
                cvd_change = 0.0
                cvd_slope = 0.0

            out["eligible_%ds" % w] = eligible
            out["trade_count_%ds" % w] = count
            out["buy_count_%ds" % w] = buy_count
            out["sell_count_%ds" % w] = sell_count
            out["buy_volume_%ds" % w] = buy_volume
            out["sell_volume_%ds" % w] = sell_volume
            out["delta_%ds" % w] = delta
            out["delta_ratio_%ds" % w] = delta_ratio
            out["count_imb_%ds" % w] = count_imbalance
            out["intensity_%ds" % w] = intensity
            out["large_ratio_%ds" % w] = large_ratio
            out["cvd_change_%ds" % w] = cvd_change
            out["cvd_slope_%ds" % w] = cvd_slope
            out["price_change_%ds_pct" % w] = price_change_pct

        output_rows.append(out)

        # Add current trade AFTER feature calculation.
        historical_sizes.append(q)

        previous_time = t

    fields = list(output_rows[0].keys())

    with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print("TRADEFLOW FEATURES V2")
    print("INPUT_ROWS =", len(data))
    print("OUTPUT_ROWS =", len(output_rows))
    print("MIN_TRADES =", MIN_TRADES)
    print("LARGE_LOOKBACK =", LARGE_LOOKBACK)
    print("LARGE_Q =", LARGE_Q)
    print("GAP_RESET_SEC =", GAP_SEC)
    print("OUTPUT =", OUTPUT)
    print("STATUS = OK")


if __name__ == "__main__":
    main()

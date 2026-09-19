import csv
import math
from collections import deque

INPUT = "matches_clean.csv"
OUTPUT = "tradeflow_features_v3.csv"

WINDOWS = (30, 60, 120)
GAP_SEC = 300.0

MIN_TRADES = 5

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
            trade_id = str(x.get("id", "")).strip()

            if not trade_id or trade_id in seen:
                continue

            try:
                t = float(x["time"])
                price = float(x["price"])
                base = float(x["base_amount"])
                side = x["side"].strip().lower()

                if not (
                    math.isfinite(t)
                    and math.isfinite(price)
                    and math.isfinite(base)
                ):
                    continue

                if t <= 0 or price <= 0 or base <= 0:
                    continue

                if side not in ("buy", "sell"):
                    continue

                # Reconstruct quote value from price * base_amount.
                # This avoids problems caused by quote_amount rounding to 0.00.
                quote = price * base

                if not math.isfinite(quote) or quote <= 0:
                    continue

                seen.add(trade_id)

                rows.append({
                    "id": trade_id,
                    "time": t,
                    "price": price,
                    "base_amount": base,
                    "quote_amount": quote,
                    "side": side,
                })

            except Exception:
                continue

    rows.sort(key=lambda x: x["time"])
    return rows


def main():
    data = load_data()

    if not data:
        print("NO_VALID_DATA")
        return

    windows = {
        w: deque()
        for w in WINDOWS
    }

    # Historical trade sizes only.
    # Current trade is added AFTER its features are calculated.
    historical_sizes = deque(maxlen=LARGE_LOOKBACK)

    output_rows = []

    segment_cvd = 0.0
    previous_time = None
    segment_id = 0

    for row in data:
        t = row["time"]
        q = row["quote_amount"]

        signed_volume = q if row["side"] == "buy" else -q

        # A gap > 5 minutes creates a new independent segment.
        if previous_time is not None and t - previous_time > GAP_SEC:
            for w in WINDOWS:
                windows[w].clear()

            historical_sizes.clear()
            segment_cvd = 0.0
            segment_id += 1

        segment_cvd += signed_volume

        out = {
            "id": row["id"],
            "time": row["time"],
            "price": row["price"],
            "base_amount": row["base_amount"],
            "quote_amount": row["quote_amount"],
            "side": row["side"],
            "segment_id": segment_id,
            "signed_volume": signed_volume,
            "segment_cvd": segment_cvd,
        }

        # Large trade threshold uses only PREVIOUS trades.
        previous_p95 = (
            quantile(list(historical_sizes), LARGE_Q)
            if historical_sizes
            else 0.0
        )

        out["large_trade"] = (
            1 if previous_p95 > 0 and q >= previous_p95 else 0
        )

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

            buy_count = sum(
                1 for x in dq
                if x[3] == "buy"
            )

            sell_count = sum(
                1 for x in dq
                if x[3] == "sell"
            )

            buy_volume = sum(
                x[1] for x in dq
                if x[3] == "buy"
            )

            sell_volume = sum(
                x[1] for x in dq
                if x[3] == "sell"
            )

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
                    x[1] for x in dq
                    if x[1] >= previous_p95
                )
                large_ratio = large_volume / total_volume
            else:
                large_ratio = 0.0

            # FIXED-WINDOW CVD RATE.
            # Do NOT divide by the tiny elapsed time between trades.
            cvd_rate = delta / float(w)

            # Signed log transformation reduces domination by very large trades.
            if cvd_rate > 0:
                cvd_rate_log = math.log1p(cvd_rate)
            elif cvd_rate < 0:
                cvd_rate_log = -math.log1p(abs(cvd_rate))
            else:
                cvd_rate_log = 0.0

            prices = [x[4] for x in dq]

            if prices:
                first_price = prices[0]

                price_change_pct = (
                    (row["price"] / first_price - 1.0) * 100.0
                    if first_price > 0
                    else 0.0
                )
            else:
                price_change_pct = 0.0

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
            out["cvd_rate_%ds" % w] = cvd_rate
            out["cvd_rate_log_%ds" % w] = cvd_rate_log
            out["price_change_%ds_pct" % w] = price_change_pct

        output_rows.append(out)

        historical_sizes.append(q)
        previous_time = t

    fields = list(output_rows[0].keys())

    with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print("TRADEFLOW FEATURES V3")
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
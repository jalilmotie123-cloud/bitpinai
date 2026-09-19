import csv
import math
from collections import deque

INPUT = "matches_clean.csv"
OUTPUT = "tradeflow_features_v1.csv"

WINDOWS = (30, 60, 120)
GAP_SEC = 300.0
LARGE_LOOKBACK = 300


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

                if (
                    not math.isfinite(t)
                    or not math.isfinite(price)
                    or not math.isfinite(base)
                    or not math.isfinite(quote)
                    or price <= 0
                    or base <= 0
                    or side not in ("buy", "sell")
                ):
                    continue

                seen.add(mid)

                rows.append({
                    "id": mid,
                    "time": t,
                    "price": price,
                    "base_amount": base,
                    "quote_amount": quote,
                    "side": side,
                })

            except Exception:
                continue

    rows.sort(key=lambda z: z["time"])
    return rows


def main():
    data = load_data()

    if not data:
        print("NO_VALID_DATA")
        return

    output_rows = []

    windows = {
        w: deque()
        for w in WINDOWS
    }

    large_history = deque(maxlen=LARGE_LOOKBACK)

    segment_cvd = 0.0
    prev_time = None

    for row in data:
        t = row["time"]
        q = row["quote_amount"]
        signed_q = q if row["side"] == "buy" else -q

        # Reset state after a large data gap.
        if prev_time is not None and t - prev_time > GAP_SEC:
            for dq in windows.values():
                dq.clear()

            large_history.clear()
            segment_cvd = 0.0

        segment_cvd += signed_q

        base_out = {
            "id": row["id"],
            "time": row["time"],
            "price": row["price"],
            "base_amount": row["base_amount"],
            "quote_amount": row["quote_amount"],
            "side": row["side"],
            "segment_cvd": segment_cvd,
        }

        # Distribution-relative large trade threshold.
        if large_history:
            hs = sorted(large_history)
            p90_index = int(0.90 * (len(hs) - 1))
            p90 = hs[p90_index]
        else:
            p90 = 0.0

        base_out["large_trade"] = 1 if p90 > 0 and q >= p90 else 0

        for w in WINDOWS:
            dq = windows[w]
            dq.append((t, q, signed_q, row["side"], row["price"]))

            while dq and t - dq[0][0] > w:
                dq.popleft()

            buy_vol = sum(x[1] for x in dq if x[3] == "buy")
            sell_vol = sum(x[1] for x in dq if x[3] == "sell")
            buy_count = sum(1 for x in dq if x[3] == "buy")
            sell_count = sum(1 for x in dq if x[3] == "sell")

            total_vol = buy_vol + sell_vol
            total_count = buy_count + sell_count

            delta = buy_vol - sell_vol

            if total_vol > 0:
                delta_ratio = delta / total_vol
            else:
                delta_ratio = 0.0

            count_imb = (
                (buy_count - sell_count) / total_count
                if total_count > 0 else 0.0
            )

            intensity = total_count / float(w)

            large_vol = 0.0
            if p90 > 0:
                large_vol = sum(x[1] for x in dq if x[1] >= p90)

            large_ratio = (
                large_vol / total_vol
                if total_vol > 0 else 0.0
            )

            prices = [x[4] for x in dq]
            first_price = prices[0] if prices else row["price"]

            price_change_pct = (
                (row["price"] / first_price - 1.0) * 100.0
                if first_price > 0 else 0.0
            )

            base_out[f"buy_vol_{w}s"] = buy_vol
            base_out[f"sell_vol_{w}s"] = sell_vol
            base_out[f"delta_{w}s"] = delta
            base_out[f"delta_ratio_{w}s"] = delta_ratio
            base_out[f"count_imb_{w}s"] = count_imb
            base_out[f"intensity_{w}s"] = intensity
            base_out[f"large_ratio_{w}s"] = large_ratio
            base_out[f"price_change_{w}s_pct"] = price_change_pct

        output_rows.append(base_out)

        large_history.append(q)
        prev_time = t

    fields = list(output_rows[0].keys())

    with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print("TRADEFLOW FEATURES V1")
    print("INPUT_ROWS =", len(data))
    print("OUTPUT_ROWS =", len(output_rows))
    print("OUTPUT =", OUTPUT)
    print("STATUS = OK")


if __name__ == "__main__":
    main()
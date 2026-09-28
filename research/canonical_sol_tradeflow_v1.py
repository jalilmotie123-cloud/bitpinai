# -*- coding: utf-8 -*-
"""
Canonical SOL tradeflow feature builder v1.

Reads the collector-owned canonical SOL matches file and creates a
deterministic feature file. No input file is modified.
"""

import argparse
import csv
import os
import statistics
import tempfile
from bisect import bisect_left, bisect_right
from collections import deque


WINDOWS_SEC = (30, 60, 120, 300, 600)
DEFAULT_INPUT = "canonical_sol_matches_v1.csv"
DEFAULT_OUTPUT = "tradeflow_features_canonical.csv"
SYMBOL = "SOL_USDT"
LARGE_TRADE_QUANTILE = 0.90


def numeric(value):
    try:
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return None
        return x
    except (TypeError, ValueError):
        return None


def event_epoch_ms(value):
    x = numeric(value)
    if x is None:
        return None
    if abs(x) > 100000000000:
        return int(x)
    if abs(x) > 1000000000:
        return int(x * 1000.0)
    return None


def load_matches(path):
    rows = []
    parser_errors = 0
    duplicate_ids = 0
    seen = set()

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            trade_id = str(row.get("id") or "").strip()
            if not trade_id:
                parser_errors += 1
                continue
            if trade_id in seen:
                duplicate_ids += 1
                continue

            event_ms = event_epoch_ms(row.get("event_time_epoch_ms"))
            if event_ms is None:
                parser_errors += 1
                continue

            price = numeric(row.get("price"))
            base = numeric(row.get("base_amount"))
            quote = numeric(row.get("quote_amount"))
            side = str(row.get("side") or "").strip().lower()

            if (
                price is None or price <= 0 or
                base is None or base < 0 or
                quote is None or quote < 0 or
                side not in ("buy", "sell")
            ):
                parser_errors += 1
                continue

            seen.add(trade_id)
            rows.append(
                {
                    "id": trade_id,
                    "event_time_ms": event_ms,
                    "price": price,
                    "base": base,
                    "quote": quote,
                    "side": side,
                }
            )

    rows.sort(key=lambda r: (r["event_time_ms"], r["id"]))
    return rows, parser_errors, duplicate_ids


def quantile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def rolling_feature_rows(matches):
    if not matches:
        return []

    times = [r["event_time_ms"] / 1000.0 for r in matches]
    prices = [r["price"] for r in matches]
    n = len(matches)

    deques = {
        w: deque() for w in WINDOWS_SEC
    }
    sums = {
        w: {
            "count": 0,
            "base": 0.0,
            "quote": 0.0,
            "buy_base": 0.0,
            "sell_base": 0.0,
            "buy_quote": 0.0,
            "sell_quote": 0.0,
        }
        for w in WINDOWS_SEC
    }
    lefts = {w: 0 for w in WINDOWS_SEC}

    output = []

    for i in range(n):
        current_time = times[i]

        for w in WINDOWS_SEC:
            q = deques[w]
            s = sums[w]
            q.append(i)

            base = matches[i]["base"]
            quote = matches[i]["quote"]
            s["count"] += 1
            s["base"] += base
            s["quote"] += quote
            if matches[i]["side"] == "buy":
                s["buy_base"] += base
                s["buy_quote"] += quote
            else:
                s["sell_base"] += base
                s["sell_quote"] += quote

            cutoff = current_time - w
            left = lefts[w]
            while q and times[q[0]] < cutoff:
                old_i = q.popleft()
                old = matches[old_i]
                s["count"] -= 1
                s["base"] -= old["base"]
                s["quote"] -= old["quote"]
                if old["side"] == "buy":
                    s["buy_base"] -= old["base"]
                    s["buy_quote"] -= old["quote"]
                else:
                    s["sell_base"] -= old["base"]
                    s["sell_quote"] -= old["quote"]
                left = old_i + 1
            lefts[w] = left

        values = {
            "event_time_epoch_ms": matches[i]["event_time_ms"],
            "event_trade_id": matches[i]["id"],
            "price": prices[i],
            "symbol": SYMBOL,
        }

        for w in WINDOWS_SEC:
            s = sums[w]
            start_i = lefts[w]
            count = s["count"]
            total_quote = s["quote"]

            delta = s["buy_quote"] - s["sell_quote"]
            delta_ratio = delta / total_quote if total_quote > 0 else 0.0

            window_quotes = [
                matches[j]["quote"]
                for j in range(start_i, i + 1)
            ]
            large_threshold = quantile(
                window_quotes,
                LARGE_TRADE_QUANTILE
            )
            large_count = 0
            if large_threshold is not None:
                large_count = sum(
                    1
                    for quote_value in window_quotes
                    if quote_value >= large_threshold
                )

            first_price = prices[start_i] if start_i <= i else prices[i]
            price_return = (
                prices[i] / first_price - 1.0
                if first_price > 0
                else 0.0
            )

            prefix = "%ss" % w
            values["%s_trade_count" % prefix] = count
            values["%s_base_volume" % prefix] = s["base"]
            values["%s_quote_volume" % prefix] = total_quote
            values["%s_buy_base_volume" % prefix] = s["buy_base"]
            values["%s_sell_base_volume" % prefix] = s["sell_base"]
            values["%s_buy_quote_volume" % prefix] = s["buy_quote"]
            values["%s_sell_quote_volume" % prefix] = s["sell_quote"]
            values["%s_cvd" % prefix] = delta
            values["%s_delta" % prefix] = delta
            values["%s_delta_ratio" % prefix] = delta_ratio
            values["%s_intensity" % prefix] = count / float(w)
            values["%s_large_trade_ratio" % prefix] = (
                large_count / float(count) if count > 0 else 0.0
            )
            values["%s_price_return" % prefix] = price_return
            values["%s_large_trade_quote_threshold" % prefix] = (
                large_threshold if large_threshold is not None else ""
            )

        output.append(values)

    return output


def atomic_write_csv(path, rows):
    if not rows:
        fields = ["event_time_epoch_ms", "event_trade_id", "price", "symbol"]
        for w in WINDOWS_SEC:
            prefix = "%ss" % w
            fields.extend(
                [
                    "%s_trade_count" % prefix,
                    "%s_base_volume" % prefix,
                    "%s_quote_volume" % prefix,
                    "%s_buy_base_volume" % prefix,
                    "%s_sell_base_volume" % prefix,
                    "%s_buy_quote_volume" % prefix,
                    "%s_sell_quote_volume" % prefix,
                    "%s_cvd" % prefix,
                    "%s_delta" % prefix,
                    "%s_delta_ratio" % prefix,
                    "%s_intensity" % prefix,
                    "%s_large_trade_ratio" % prefix,
                    "%s_price_return" % prefix,
                    "%s_large_trade_quote_threshold" % prefix,
                ]
            )
    else:
        fields = list(rows[0].keys())

    directory = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.exists(directory):
        os.makedirs(directory)

    fd, temp_path = tempfile.mkstemp(
        prefix=".tradeflow_",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build deterministic canonical SOL tradeflow features."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)

    print("CANONICAL SOL TRADEFLOW BUILDER V1")
    print("INPUT =", input_path)
    print("OUTPUT =", output_path)
    print("WINDOWS_SEC =", WINDOWS_SEC)
    print("LARGE_TRADE_DEFINITION = current-window quote-volume >= P90")
    print("NO FUTURE DATA USED")
    print("[LOAD] matches")

    if not os.path.exists(input_path):
        raise SystemExit("MISSING_INPUT: %s" % input_path)

    matches, parser_errors, duplicate_ids = load_matches(input_path)
    print(
        "[LOAD] rows=%d parser_errors=%d duplicates_ignored=%d"
        % (len(matches), parser_errors, duplicate_ids)
    )

    print("[BUILD] rolling windows")
    features = rolling_feature_rows(matches)
    print("[BUILD] complete rows=%d" % len(features))

    print("[OUTPUT] atomic write")
    atomic_write_csv(output_path, features)
    print("[OUTPUT] complete")

    print(
        "SUMMARY | input_rows=%d | valid_rows=%d | parser_errors=%d | duplicates_ignored=%d | feature_rows=%d"
        % (
            len(matches) + parser_errors + duplicate_ids,
            len(matches),
            parser_errors,
            duplicate_ids,
            len(features),
        )
    )


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Canonical SOL collection manifest builder v1.

Reads collector-owned canonical files and writes research/data_manifest.json.
It never rewrites the collected data.
"""

import argparse
import csv
import json
import os
import statistics
from datetime import datetime, timezone

from canonical_sol_market_collector_v1 import (
    GAP_OUTAGE_SEC,
    GAP_WARNING_SEC,
    local_timezone_label,
    parse_timestamp,
)
from canonical_sol_matches_collector_v1 import event_epoch_ms


DEFAULT_MARKET = "canonical_sol_market_v1.csv"
DEFAULT_MATCHES = "canonical_sol_matches_v1.csv"
DEFAULT_TRADEFLOW = "tradeflow_features_canonical.csv"
DEFAULT_OUTPUT = os.path.join("research", "data_manifest.json")


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def quantile(values, p):
    vals = sorted(values)
    if not vals:
        return None
    pos = (len(vals) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def gap_summary(times):
    unique = sorted(set(times))
    gaps = [
        b - a for a, b in zip(unique, unique[1:]) if b >= a
    ]
    return {
        "median_sec": statistics.median(gaps) if gaps else None,
        "p90_sec": quantile(gaps, 0.90),
        "p95_sec": quantile(gaps, 0.95),
        "p99_sec": quantile(gaps, 0.99),
        "max_sec": max(gaps) if gaps else None,
        "warning_gaps": sum(g > GAP_WARNING_SEC for g in gaps),
        "outage_gaps": sum(g > GAP_OUTAGE_SEC for g in gaps),
    }


def quality_flags_from_common(
    rows,
    times,
    invalid_rows,
    duplicate_ids,
    parser_errors,
):
    flags = []
    if invalid_rows:
        flags.append("INVALID_ROWS_PRESENT")
    if duplicate_ids:
        flags.append("DUPLICATES_PRESENT")
    if parser_errors:
        flags.append("PARSER_ERRORS_PRESENT")
    if times:
        gaps = gap_summary(times)
        if gaps["warning_gaps"]:
            flags.append("WARNING_GAPS_PRESENT")
        if gaps["outage_gaps"]:
            flags.append("OUTAGE_GAPS_PRESENT")
    if any(
        str(row.get("state_reset") or "0") == "1"
        for row in rows
        if "state_reset" in row
    ):
        flags.append("STATE_RESETS_PRESENT")
    if any(
        str(row.get("continuity_flag") or "normal") == "outage"
        for row in rows
        if "continuity_flag" in row
    ):
        flags.append("OUTAGE_FLAG_PRESENT")
    return sorted(set(flags))


def profile_file(path, kind):
    result = {
        "file": os.path.abspath(path),
        "kind": kind,
        "exists": os.path.exists(path),
        "host_local_timezone": local_timezone_label(),
    }
    if not os.path.exists(path):
        result["data_quality_flags"] = ["MISSING_FILE"]
        return result

    rows = read_csv(path)
    result["rows"] = len(rows)
    if not rows:
        result.update(
            first_timestamp=None,
            last_timestamp=None,
            valid_rows=0,
            parser_errors=0,
            duplicates_removed=0,
            gaps=gap_summary([]),
            reconnects=0,
            data_quality_flags=["EMPTY_FILE"],
        )
        return result

    times = []
    valid_rows = 0
    parser_errors = 0
    duplicate_ids = 0
    ids = set()
    invalid_rows = 0

    if kind == "market":
        for row in rows:
            try:
                t, _ = parse_timestamp(row.get("received_at_epoch_ms"))
                if t is None:
                    parser_errors += 1
                    continue
                times.append(t)
                bid = float(row.get("bid"))
                ask = float(row.get("ask"))
                if bid <= 0 or ask <= 0 or ask < bid:
                    invalid_rows += 1
                else:
                    valid_rows += 1
            except (TypeError, ValueError):
                parser_errors += 1
        reconnects = max(
            [int(row.get("reconnect_count") or 0) for row in rows]
            or [0]
        )
    elif kind == "matches":
        for row in rows:
            try:
                t = event_epoch_ms(row.get("event_time_epoch_ms"))
                if t is None:
                    parser_errors += 1
                else:
                    times.append(t / 1000.0)
                trade_id = str(row.get("id") or "")
                if trade_id:
                    if trade_id in ids:
                        duplicate_ids += 1
                    else:
                        ids.add(trade_id)
                price = float(row.get("price"))
                base = float(row.get("base_amount"))
                quote = float(row.get("quote_amount"))
                if price <= 0 or base < 0 or quote < 0:
                    invalid_rows += 1
                else:
                    valid_rows += 1
            except (TypeError, ValueError):
                parser_errors += 1
        reconnects = max(
            [int(row.get("reconnect_count") or 0) for row in rows]
            or [0]
        )
    else:
        for row in rows:
            t = event_epoch_ms(row.get("event_time_epoch_ms"))
            if t is not None:
                times.append(t / 1000.0)
                valid_rows += 1
            else:
                parser_errors += 1
        reconnects = 0

    times.sort()
    duplicates_removed = duplicate_ids
    result.update(
        first_timestamp=(
            datetime.fromtimestamp(times[0], timezone.utc).isoformat()
            if times else None
        ),
        last_timestamp=(
            datetime.fromtimestamp(times[-1], timezone.utc).isoformat()
            if times else None
        ),
        valid_rows=valid_rows,
        parser_errors=parser_errors,
        duplicates_removed=duplicates_removed,
        gaps=gap_summary(times),
        reconnects=reconnects,
        data_quality_flags=quality_flags_from_common(
            rows,
            times,
            invalid_rows,
            duplicate_ids,
            parser_errors,
        ),
    )

    if kind == "market":
        state_reset_count = sum(
            1 for row in rows
            if str(row.get("state_reset") or "0") == "1"
        )
        result["state_reset_count"] = state_reset_count
        result["server_timestamp_available"] = any(
            str(row.get("server_timestamp_available")).lower() == "true"
            for row in rows
        )
    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build canonical SOL collection data manifest."
    )
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--matches", default=DEFAULT_MATCHES)
    parser.add_argument("--tradeflow", default=DEFAULT_TRADEFLOW)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main():
    args = parse_args()
    items = [
        profile_file(os.path.abspath(args.market), "market"),
        profile_file(os.path.abspath(args.matches), "matches"),
        profile_file(os.path.abspath(args.tradeflow), "tradeflow"),
    ]

    manifest = {
        "schema_versions": {
            "market": "market_canonical_v1",
            "matches": "matches_canonical_v1",
            "tradeflow": "tradeflow_canonical_v1",
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "host_local_timezone": local_timezone_label(),
        "files": items,
        "notes": [
            "Manifest generation is read-only with respect to collected data files.",
            "Reconnect counts are derived from collector reconnect_count fields.",
            "Raw observation N is not an independent-sample count.",
        ],
    }

    output_path = os.path.abspath(args.output)
    directory = os.path.dirname(output_path) or "."
    if not os.path.exists(directory):
        os.makedirs(directory)

    temp_path = output_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, output_path)

    print("MANIFEST =", output_path)
    for item in items:
        print(
            "%s | exists=%s | rows=%s | valid=%s | reconnects=%s | flags=%s"
            % (
                item["kind"],
                item["exists"],
                item.get("rows", 0),
                item.get("valid_rows", 0),
                item.get("reconnects", 0),
                ",".join(item.get("data_quality_flags", [])),
            )
        )


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Selective 24h Feasibility Test V1.

Research-only. No orders, no network/API access, no ML, no threshold sweeps.
Reads existing local Bitpin datasets and writes only task-owned result files.
"""

import argparse
import csv
import math
import os
import statistics
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone

from canonical_sol_market_collector_v1 import parse_timestamp

HORIZON_SEC = 86400.0
SCORE_THRESHOLD = 1.50
FEE_SIDE = 0.0035
SLIPPAGE_BPS = (0, 5, 10, 20, 30)
MIN_ENTRY_SEPARATION_SEC = 86400.0
MAX_ENTRY_ALIGNMENT_SEC = 30.0
MIN_HOLDOUT_SELECTED_N = 5
MIN_COVERAGE_DAYS = 30.0
SHORT_EXECUTION_PROVEN = False

MARKET_CANDIDATES = ("market_data_v3.csv", "market_data_v2.csv")
TRADEFLOW_FILE = "tradeflow_features_v3.csv"

# Fixed feature choice. CVD aliases are only schema-compatible names for the
# same requested economic concept; no candidate search is performed.
FEATURE_NAMES = (
    "obi10",
    "ofi_norm",
)
CVD_ALIASES = (
    "cvd_rate_log_60s",
    "cvd_rate_60s",
    "cvd_60s",
)

OUTPUT_CSV = "research/selective_24h_results.csv"
OUTPUT_TXT = "research/selective_24h_report.txt"

SYMBOL_ALIASES = {"SOL_USDT", "SOL/USDT", "SOL-USDT", "SOLUSDT"}


def clean_number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def q(values, p):
    vals = sorted(x for x in values if x is not None and math.isfinite(x))
    if not vals:
        return None
    pos = (len(vals) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def summary(values):
    vals = [x for x in values if x is not None and math.isfinite(x)]
    if not vals:
        return {
            "N": 0,
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "win_rate": None,
            "profit_factor": None,
            "cumulative_arithmetic": None,
            "compounded": None,
            "max_drawdown": None,
        }

    gains = sum(x for x in vals if x > 0)
    losses = sum(-x for x in vals if x < 0)
    pf = None if losses == 0 else gains / losses
    if losses == 0 and gains > 0:
        pf = float("inf")

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for x in vals:
        equity *= (1.0 + x)
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = 1.0 - equity / peak
            if dd > max_dd:
                max_dd = dd

    return {
        "N": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "p25": q(vals, 0.25),
        "p75": q(vals, 0.75),
        "p90": q(vals, 0.90),
        "win_rate": sum(x > 0 for x in vals) / len(vals),
        "profit_factor": pf,
        "cumulative_arithmetic": sum(vals),
        "compounded": equity - 1.0,
        "max_drawdown": max_dd,
    }


def pct(x):
    return "" if x is None else x * 100.0


def row_dict(rows):
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


def field(row, names):
    for name in names:
        if name.lower() in row:
            return row[name.lower()]
    return None


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def is_sol(row):
    symbol = field(row, ("symbol", "market", "pair", "ticker"))
    if symbol is None or str(symbol).strip() == "":
        return True
    return str(symbol).strip().upper() in SYMBOL_ALIASES


def load_market(path):
    rows = row_dict(read_rows(path))
    parsed = []
    schema = rows[0] if rows else {}

    required = ("time", "bid", "ask", "mid", "obi10", "ofi_norm")
    missing = [name for name in required if name not in schema]

    if missing:
        return [], {
            "path": path,
            "rows": len(rows),
            "error": "MISSING_MARKET_COLUMNS:" + ",".join(missing),
        }

    parser_errors = 0
    invalid = 0
    for row in rows:
        if not is_sol(row):
            continue
        t, kind = parse_timestamp(field(row, ("time",)))
        bid = clean_number(field(row, ("bid",)))
        ask = clean_number(field(row, ("ask",)))
        mid = clean_number(field(row, ("mid",)))
        obi = clean_number(field(row, ("obi10",)))
        ofi = clean_number(field(row, ("ofi_norm",)))

        if t is None:
            parser_errors += 1
            continue
        if (
            bid is None or ask is None or mid is None or
            obi is None or ofi is None or
            bid <= 0 or ask <= 0 or mid <= 0 or ask < bid
        ):
            invalid += 1
            continue

        parsed.append({
            "time": t,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "obi10": obi,
            "ofi_norm": ofi,
            "timestamp_kind": kind,
        })

    parsed.sort(key=lambda x: x["time"])
    dedup = []
    seen = set()
    duplicate_timestamps = 0
    for row in parsed:
        if row["time"] in seen:
            duplicate_timestamps += 1
            continue
        seen.add(row["time"])
        dedup.append(row)

    gaps = [
        b["time"] - a["time"]
        for a, b in zip(dedup, dedup[1:])
        if b["time"] >= a["time"]
    ]
    info = {
        "path": path,
        "rows": len(rows),
        "sol_rows": sum(1 for r in rows if is_sol(r)),
        "valid_rows": len(dedup),
        "parser_errors": parser_errors,
        "invalid_rows": invalid,
        "duplicate_timestamps_removed": duplicate_timestamps,
        "start": dedup[0]["time"] if dedup else None,
        "end": dedup[-1]["time"] if dedup else None,
        "median_interval": statistics.median(gaps) if gaps else None,
        "p90_interval": q(gaps, 0.90),
        "p95_interval": q(gaps, 0.95),
        "p99_interval": q(gaps, 0.99),
        "max_gap": max(gaps) if gaps else None,
        "schema_valid": not missing,
    }
    return dedup, info


def select_market(market_profiles):
    valid = [
        (market, info)
        for market, info in market_profiles
        if info.get("schema_valid") and market
    ]
    if not valid:
        return None, None, "No valid market_data_v3/v2 executable schema."

    v3 = next(
        ((m, i) for m, i in valid if os.path.basename(i["path"]) == "market_data_v3.csv"),
        None,
    )
    if v3:
        return v3[0], v3[1], (
            "market_data_v3.csv selected as primary source because it has the required "
            "executable SOL schema and is explicitly preferred by the test specification."
        )

    return valid[0][0], valid[0][1], (
        "market_data_v2.csv used only as fallback because market_data_v3.csv was unavailable "
        "or failed executable schema validation."
    )


def load_tradeflow(path):
    rows = row_dict(read_rows(path))
    if not rows:
        return [], {
            "path": path,
            "rows": 0,
            "valid_rows": 0,
            "error": "EMPTY_TRADEFLOW",
        }

    aliases = CVD_ALIASES
    time_key_exists = "time" in rows[0]
    cvd_key = next((x for x in aliases if x in rows[0]), None)
    if not time_key_exists or cvd_key is None:
        missing = []
        if not time_key_exists:
            missing.append("time")
        if cvd_key is None:
            missing.append("one_of:" + ",".join(aliases))
        return [], {
            "path": path,
            "rows": len(rows),
            "valid_rows": 0,
            "error": "MISSING_TRADEFLOW_COLUMNS:" + ",".join(missing),
        }

    out = []
    parser_errors = 0
    invalid = 0
    for row in rows:
        if not is_sol(row):
            continue
        t, kind = parse_timestamp(row.get("time"))
        cvd = clean_number(row.get(cvd_key))
        if t is None:
            parser_errors += 1
            continue
        if cvd is None:
            invalid += 1
            continue
        out.append({
            "time": t,
            "cvd": cvd,
            "timestamp_kind": kind,
        })

    out.sort(key=lambda x: x["time"])
    duplicate_timestamps = 0
    dedup = []
    for row in out:
        if dedup and row["time"] == dedup[-1]["time"]:
            # Preserve the first row deterministically; duplicate feature timestamps
            # are not independent signals.
            duplicate_timestamps += 1
            continue
        dedup.append(row)

    return dedup, {
        "path": path,
        "rows": len(rows),
        "valid_rows": len(dedup),
        "parser_errors": parser_errors,
        "invalid_rows": invalid,
        "duplicate_timestamps_removed": duplicate_timestamps,
        "cvd_column_used": cvd_key,
        "start": dedup[0]["time"] if dedup else None,
        "end": dedup[-1]["time"] if dedup else None,
    }


def build_signal_records(market, tradeflow):
    market_times = [x["time"] for x in market]
    records = []
    rejected = Counter()

    for signal in tradeflow:
        signal_time = signal["time"]

        feature_idx = bisect_right(market_times, signal_time) - 1
        entry_idx = bisect_left(market_times, signal_time)

        if feature_idx < 0:
            rejected["no_prior_market_feature_snapshot"] += 1
            continue
        if entry_idx >= len(market):
            rejected["no_future_market_entry_snapshot"] += 1
            continue

        feature_snapshot = market[feature_idx]
        entry_snapshot = market[entry_idx]
        entry_delay = entry_snapshot["time"] - signal_time
        feature_age = signal_time - feature_snapshot["time"]

        if entry_delay < 0:
            rejected["negative_entry_delay"] += 1
            continue
        if entry_delay > MAX_ENTRY_ALIGNMENT_SEC:
            rejected["entry_delay_gt_30s"] += 1
            continue

        # Feature snapshot is at/before signal; execution snapshot is at/after signal.
        records.append({
            "signal_time": signal_time,
            "feature_snapshot_time": feature_snapshot["time"],
            "entry_snapshot_time": entry_snapshot["time"],
            "entry_delay_sec": entry_delay,
            "feature_age_sec": feature_age,
            "obi10": feature_snapshot["obi10"],
            "ofi_norm": feature_snapshot["ofi_norm"],
            "cvd_rate_60s": signal["cvd"],
            "entry_bid": entry_snapshot["bid"],
            "entry_ask": entry_snapshot["ask"],
            "entry_mid": entry_snapshot["mid"],
            "entry_spread_pct": (entry_snapshot["ask"] / entry_snapshot["bid"] - 1.0) * 100.0,
        })

    records.sort(key=lambda x: x["signal_time"])
    return records, rejected


def split_records(records):
    n = len(records)
    train_end = int(n * 0.50)
    validation_end = train_end + int(n * 0.20)

    train = records[:train_end]
    validation = records[train_end:validation_end]
    holdout = records[validation_end:]
    return train, validation, holdout


def fit_scaling(train):
    scaling = {}
    for name in ("obi10", "ofi_norm", "cvd_rate_60s"):
        values = [x[name] for x in train if x[name] is not None]
        if not values:
            raise ValueError("NO_TRAIN_VALUES:" + name)
        mean = statistics.mean(values)
        std = statistics.pstdev(values)
        if std <= 0:
            raise ValueError("ZERO_TRAIN_STD:" + name)
        scaling[name] = {"mean": mean, "std": std}
    return scaling


def score_record(record, scaling):
    zs = []
    for name in ("obi10", "ofi_norm", "cvd_rate_60s"):
        s = scaling[name]
        zs.append((record[name] - s["mean"]) / s["std"])
    return sum(zs) / 3.0


def score_records(records, scaling):
    out = []
    for record in records:
        row = dict(record)
        row["score"] = score_record(record, scaling)
        row["direction"] = (
            "LONG" if row["score"] >= SCORE_THRESHOLD
            else "SHORT" if row["score"] <= -SCORE_THRESHOLD
            else "NONE"
        )
        out.append(row)
    return out


def last_snapshot_at_or_before(times, start_idx, target):
    return bisect_right(times, target, lo=start_idx + 1) - 1


def evaluate_trade(market, entry_index, side):
    times = [x["time"] for x in market]
    entry = market[entry_index]
    exit_target = entry["time"] + HORIZON_SEC
    exit_index = last_snapshot_at_or_before(times, entry_index, exit_target)

    # Use the last market snapshot at or before the 24h target, matching the
    # canonical feasibility convention. There must be a snapshot after entry.
    if exit_index <= entry_index:
        return None

    exit_row = market[exit_index]
    window = market[entry_index + 1:exit_index + 1]
    if not window:
        return None

    if side == "LONG":
        gross = exit_row["bid"] / entry["ask"] - 1.0
        net = (
            exit_row["bid"] * (1.0 - FEE_SIDE) /
            (entry["ask"] * (1.0 + FEE_SIDE)) - 1.0
        )
        mfe = max(x["bid"] for x in window) / entry["ask"] - 1.0
        mae = min(x["bid"] for x in window) / entry["ask"] - 1.0
    else:
        gross = entry["bid"] / exit_row["ask"] - 1.0
        net = (
            entry["bid"] * (1.0 - FEE_SIDE) /
            (exit_row["ask"] * (1.0 + FEE_SIDE)) - 1.0
        )
        favorable = [entry["bid"] / x["ask"] - 1.0 for x in window]
        adverse = [entry["bid"] / x["ask"] - 1.0 for x in window]
        mfe = max(favorable)
        mae = min(adverse)

    return {
        "entry_time": entry["time"],
        "exit_time": exit_row["time"],
        "side": side,
        "gross_return": gross,
        "net_return": net,
        "trading_cost": gross - net,
        "entry_spread_pct": (entry["ask"] / entry["bid"] - 1.0) * 100.0,
        "exit_spread_pct": (exit_row["ask"] / exit_row["bid"] - 1.0) * 100.0,
        "mfe": mfe,
        "mae": mae,
    }


def attach_targets(scored, market):
    market_times = [x["time"] for x in market]
    out = []
    rejected = Counter()
    for row in scored:
        if row["direction"] == "NONE":
            continue
        idx = bisect_left(market_times, row["entry_snapshot_time"])
        if idx >= len(market_times):
            rejected["entry_not_found"] += 1
            continue
        trade = evaluate_trade(market, idx, row["direction"])
        if trade is None:
            rejected["no_24h_exit"] += 1
            continue
        merged = dict(row)
        merged.update(trade)
        out.append(merged)
    return out, rejected


def select_nonoverlapping(rows):
    selected = []
    last_entry = None
    for row in sorted(rows, key=lambda x: (x["entry_time"], x["signal_time"], x["side"])):
        if last_entry is None or row["entry_time"] >= last_entry + MIN_ENTRY_SEPARATION_SEC:
            selected.append(row)
            last_entry = row["entry_time"]
    return selected


def evaluate_all_baseline(records, market, side):
    rows = []
    market_times = [x["time"] for x in market]
    for record in records:
        idx = bisect_left(market_times, record["entry_snapshot_time"])
        if idx >= len(market):
            continue
        trade = evaluate_trade(market, idx, side)
        if trade is None:
            continue
        row = dict(record)
        row["score"] = ""
        row["direction"] = side
        row.update(trade)
        rows.append(row)
    return rows


def split_label(t, ranges):
    for label, lo, hi in ranges:
        if lo <= t < hi or (label == ranges[-1][0] and lo <= t <= hi):
            return label
    return "UNKNOWN"


def add_block_stats(report_rows, rows, ranges, name):
    for label, lo, hi in ranges:
        subset = [x for x in rows if lo <= x["entry_time"] < hi or (label == ranges[-1][0] and lo <= x["entry_time"] <= hi)]
        s = summary([x["net_return"] for x in subset])
        report_rows.append({
            "section": "block",
            "group": name,
            "period": label,
            "N": s["N"],
            "mean_net": pct(s["mean"]),
            "median_net": pct(s["median"]),
            "win_rate": pct(s["win_rate"]),
            "p25": pct(s["p25"]),
            "p75": pct(s["p75"]),
            "p90": pct(s["p90"]),
            "profit_factor": s["profit_factor"],
            "cumulative_arithmetic": pct(s["cumulative_arithmetic"]),
            "compounded": pct(s["compounded"]),
            "max_drawdown": pct(s["max_drawdown"]),
        })


def make_time_ranges(start, end, count):
    width = (end - start) / float(count)
    if width <= 0:
        return [("BLOCK1", start, end)]
    ranges = []
    for i in range(count):
        lo = start + i * width
        hi = end if i == count - 1 else start + (i + 1) * width
        ranges.append(("BLOCK%d" % (i + 1), lo, hi))
    return ranges


def determine_primary_status(
    primary_summary,
    baseline_mean,
    cost_robust,
    positive_block_count,
    sufficient_sample,
    sufficient_coverage,
):
    """Apply the existing gate to the economically evaluated primary side."""
    if not sufficient_sample or not sufficient_coverage:
        return "INCONCLUSIVE"

    median_positive = (
        primary_summary["median"] is not None and
        primary_summary["median"] > 0
    )
    holdout_positive = (
        primary_summary["mean"] is not None and
        primary_summary["mean"] > 0 and
        primary_summary["cumulative_arithmetic"] is not None and
        primary_summary["cumulative_arithmetic"] > 0
    )
    matched_improvement = (
        primary_summary["mean"] - baseline_mean
        if primary_summary["mean"] is not None and baseline_mean is not None
        else None
    )
    clear_improvement = (
        matched_improvement is not None and
        matched_improvement >= 0.0025
    )
    multiple_blocks = positive_block_count >= 2

    if (
        holdout_positive and
        median_positive and
        cost_robust and
        multiple_blocks and
        clear_improvement
    ):
        return "GO-FOR-FURTHER-RESEARCH"

    if (
        primary_summary["mean"] is not None and
        (
            primary_summary["mean"] <= 0 or
            primary_summary["cumulative_arithmetic"] <= 0 or
            (primary_summary["median"] is not None and primary_summary["median"] <= 0)
        )
    ):
        return "NO-GO"

    return "INCONCLUSIVE"


def main():
    parser = argparse.ArgumentParser(description="Selective 24h SOL feasibility test v1.")
    parser.add_argument("--market", default=None)
    parser.add_argument("--tradeflow", default=TRADEFLOW_FILE)
    parser.add_argument("--output-csv", default=OUTPUT_CSV)
    parser.add_argument("--output-txt", default=OUTPUT_TXT)
    args = parser.parse_args()

    print("SELECTIVE 24H FEASIBILITY V1")
    print("NETWORK_ACCESS = NONE")
    print("HORIZON_SEC = 86400")
    print("SCORE_THRESHOLD = %.2f (fixed, pre-declared)" % SCORE_THRESHOLD)
    print("ENTRY_SEPARATION_SEC = %.0f" % MIN_ENTRY_SEPARATION_SEC)
    print("FEE_SIDE = %.6f (assumption)" % FEE_SIDE)

    market_candidates = (
        [args.market] if args.market else list(MARKET_CANDIDATES)
    )
    profiles = []
    for path in market_candidates:
        if not os.path.exists(path):
            profiles.append(([], {
                "path": path,
                "exists": False,
                "schema_valid": False,
            }))
            print("[SCHEMA] %s MISSING" % path)
            continue
        market, info = load_market(path)
        info["exists"] = True
        profiles.append((market, info))
        print(
            "[SCHEMA] %s rows=%s valid_SOL=%s start=%s end=%s median_interval=%s"
            % (
                path,
                info.get("rows", 0),
                info.get("valid_rows", 0),
                info.get("start"),
                info.get("end"),
                info.get("median_interval"),
            )
        )

    market, market_info, selection_reason = select_market(profiles)
    if market is None:
        raise SystemExit("NO_VALID_MARKET_SOURCE")
    print("[MARKET] canonical=%s" % market_info["path"])
    print("[MARKET] %s" % selection_reason)

    if not os.path.exists(args.tradeflow):
        raise SystemExit("MISSING_TRADEFLOW:" + args.tradeflow)

    tradeflow, tf_info = load_tradeflow(args.tradeflow)
    print(
        "[SCHEMA] tradeflow=%s rows=%s valid=%s cvd=%s start=%s end=%s"
        % (
            args.tradeflow,
            tf_info.get("rows", 0),
            tf_info.get("valid_rows", 0),
            tf_info.get("cvd_column_used", "N/A"),
            tf_info.get("start"),
            tf_info.get("end"),
        )
    )

    if not tradeflow:
        raise SystemExit("NO_VALID_TRADEFLOW")

    records, alignment_rejected = build_signal_records(market, tradeflow)
    if len(records) < 10:
        raise SystemExit(
            "TOO_FEW_ALIGNED_SIGNAL_RECORDS:%d rejected=%r"
            % (len(records), dict(alignment_rejected))
        )

    train, validation, holdout = split_records(records)
    print(
        "[SPLIT] train=%d validation=%d holdout=%d"
        % (len(train), len(validation), len(holdout))
    )
    print(
        "[SPLIT] train=%s..%s validation=%s..%s holdout=%s..%s"
        % (
            train[0]["signal_time"], train[-1]["signal_time"],
            validation[0]["signal_time"], validation[-1]["signal_time"],
            holdout[0]["signal_time"], holdout[-1]["signal_time"],
        )
    )

    scaling = fit_scaling(train)
    print("[SCALING] fitted on train only")
    for name in ("obi10", "ofi_norm", "cvd_rate_60s"):
        print(
            "[SCALING] %s mean=%.10g std=%.10g"
            % (name, scaling[name]["mean"], scaling[name]["std"])
        )

    scored_train = score_records(train, scaling)
    scored_validation = score_records(validation, scaling)
    scored_holdout = score_records(holdout, scaling)

    # Validation is sanity-only. No selection rule is altered after observing it.
    selected_train = select_nonoverlapping(
        [x for x in scored_train if x["direction"] in ("LONG", "SHORT")]
    )
    selected_validation = select_nonoverlapping(
        [x for x in scored_validation if x["direction"] in ("LONG", "SHORT")]
    )
    selected_holdout = select_nonoverlapping(
        [x for x in scored_holdout if x["direction"] in ("LONG", "SHORT")]
    )

    # Bid/ask quotes alone do not prove executable short/margin mechanics.
    # Long is evaluated; short stays INCONCLUSIVE unless explicitly proven.
    executable_train = (
        [x for x in selected_train if x["direction"] == "LONG"]
        if not SHORT_EXECUTION_PROVEN else selected_train
    )
    executable_validation = (
        [x for x in selected_validation if x["direction"] == "LONG"]
        if not SHORT_EXECUTION_PROVEN else selected_validation
    )
    executable_holdout = (
        [x for x in selected_holdout if x["direction"] == "LONG"]
        if not SHORT_EXECUTION_PROVEN else selected_holdout
    )

    train_trades, train_reject = attach_targets(executable_train, market)
    validation_trades, validation_reject = attach_targets(executable_validation, market)
    holdout_trades, holdout_reject = attach_targets(executable_holdout, market)

    baseline_train_long = evaluate_all_baseline(train, market, "LONG")
    baseline_validation_long = evaluate_all_baseline(validation, market, "LONG")
    baseline_holdout_long = evaluate_all_baseline(holdout, market, "LONG")

    if SHORT_EXECUTION_PROVEN:
        baseline_train_short = evaluate_all_baseline(train, market, "SHORT")
        baseline_validation_short = evaluate_all_baseline(validation, market, "SHORT")
        baseline_holdout_short = evaluate_all_baseline(holdout, market, "SHORT")
    else:
        baseline_train_short = []
        baseline_validation_short = []
        baseline_holdout_short = []

    selected_long = [x for x in holdout_trades if x["side"] == "LONG"]
    selected_short = [x for x in holdout_trades if x["side"] == "SHORT"]
    selected_both = holdout_trades
    primary_group_name = (
        "selected_long_plus_short"
        if SHORT_EXECUTION_PROVEN else
        "selected_long_primary"
    )
    primary_selected = (
        selected_both
        if SHORT_EXECUTION_PROVEN else
        selected_long
    )

    # Independent-entry primary sequence: with unproven short execution,
    # Long-only spot execution is the primary economic result.
    holdout_summary = summary([x["net_return"] for x in primary_selected])
    baseline_summary = summary([x["net_return"] for x in baseline_holdout_long])
    baseline_short_summary = summary([x["net_return"] for x in baseline_holdout_short])
    selected_long_summary = summary([x["net_return"] for x in selected_long])
    selected_short_summary = summary([x["net_return"] for x in selected_short])

    coverage_days = (
        records[-1]["signal_time"] - records[0]["signal_time"]
    ) / 86400.0
    holdout_coverage_days = (
        holdout[-1]["signal_time"] - holdout[0]["signal_time"]
    ) / 86400.0 if len(holdout) > 1 else 0.0

    ranges = make_time_ranges(records[0]["signal_time"], records[-1]["signal_time"], 4)
    block_rows = []
    add_block_stats(block_rows, primary_selected, ranges, primary_group_name)
    add_block_stats(block_rows, baseline_holdout_long, ranges, "baseline_all_long")
    add_block_stats(block_rows, baseline_holdout_short, ranges, "baseline_all_short")

    # Fixed cost sensitivity, no tuning.
    sensitivity = []
    for name, values in (
        (primary_group_name, [x["net_return"] for x in primary_selected]),
        ("baseline_all_long", [x["net_return"] for x in baseline_holdout_long]),
        ("baseline_all_short", [x["net_return"] for x in baseline_holdout_short]),
    ):
        for slip in SLIPPAGE_BPS:
            vals = [x - slip / 10000.0 for x in values]
            s = summary(vals)
            sensitivity.append({
                "section": "sensitivity",
                "group": name,
                "slippage_bps": slip,
                "N": s["N"],
                "mean_net": pct(s["mean"]),
                "median_net": pct(s["median"]),
                "win_rate": pct(s["win_rate"]),
                "cumulative_arithmetic": pct(s["cumulative_arithmetic"]),
                "compounded": pct(s["compounded"]),
                "max_drawdown": pct(s["max_drawdown"]),
            })

    # Deterministic gate. Coverage/sample sufficiency is checked before calling
    # a positive result a GO; raw N is not treated as independent outside the
    # 24h-separated selected sequence.
    improvement = None
    if holdout_summary["mean"] is not None and baseline_summary["mean"] is not None:
        improvement = holdout_summary["mean"] - baseline_summary["mean"]

    stable_blocks = [
        r for r in block_rows
        if r["group"] == primary_group_name and r["N"] > 0
    ]
    positive_block_count = sum(
        1 for r in stable_blocks
        if r["mean_net"] != "" and r["mean_net"] > 0
    )

    sufficient_sample = holdout_summary["N"] >= MIN_HOLDOUT_SELECTED_N
    sufficient_coverage = coverage_days >= MIN_COVERAGE_DAYS
    cost_robust = all(
        x["mean_net"] > 0
        for x in sensitivity
        if x["group"] == "selected_long_plus_short"
        and x["slippage_bps"] in (0, 5, 10)
    )
    median_positive = (
        holdout_summary["median"] is not None and
        holdout_summary["median"] > 0
    )
    holdout_positive = (
        holdout_summary["mean"] is not None and
        holdout_summary["mean"] > 0 and
        holdout_summary["cumulative_arithmetic"] is not None and
        holdout_summary["cumulative_arithmetic"] > 0
    )
    selected_long_n = len(selected_long)
    selected_short_n = len(selected_short)
    if not SHORT_EXECUTION_PROVEN:
        # Long-only spot baseline is the sole baseline used by the primary gate.
        direction_matched_baseline_mean = baseline_summary["mean"]
    else:
        direction_matched_baseline_mean = None
        baseline_parts = []
        if selected_long_n > 0 and baseline_summary["mean"] is not None:
            baseline_parts.append((selected_long_n, baseline_summary["mean"]))
    if selected_short_n > 0 and baseline_short_summary["mean"] is not None:
        baseline_parts.append((selected_short_n, baseline_short_summary["mean"]))
    if SHORT_EXECUTION_PROVEN and baseline_parts:
        direction_matched_baseline_mean = (
            sum(weight * value for weight, value in baseline_parts) /
            sum(weight for weight, _ in baseline_parts)
        )
    matched_improvement = (
        holdout_summary["mean"] - direction_matched_baseline_mean
        if holdout_summary["mean"] is not None and direction_matched_baseline_mean is not None
        else None
    )
    clear_improvement = (
        matched_improvement is not None and
        matched_improvement >= 0.0025
    )
    no_tiny_sample = sufficient_sample
    multiple_blocks = positive_block_count >= 2

    status = determine_primary_status(
        primary_summary=holdout_summary,
        baseline_mean=direction_matched_baseline_mean,
        cost_robust=cost_robust,
        positive_block_count=positive_block_count,
        sufficient_sample=sufficient_sample,
        sufficient_coverage=sufficient_coverage,
    )

    report = []
    report.append("SELECTIVE 24H FEASIBILITY TEST V1")
    report.append("=" * 72)
    report.append("Market source: %s" % market_info["path"])
    report.append("Selection reason: %s" % selection_reason)
    report.append("Horizon: 86400 sec (24h)")
    report.append("Feature set: OBI10 + OFI_norm + CVD60 signed rate")
    report.append("Score: mean of train-fitted z-scores")
    report.append("Fixed selection: Long >= %.2f; Short <= -%.2f" % (SCORE_THRESHOLD, SCORE_THRESHOLD))
    report.append("No feature/threshold changes after validation or holdout.")
    report.append("Long execution: ASK -> future BID")
    report.append("Short execution: BID -> future ASK ONLY IF mechanics proven")
    report.append("SHORT_EXECUTION_PROVEN=%s" % SHORT_EXECUTION_PROVEN)
    report.append("Fee: %.4f%% per side (configurable assumption)" % (FEE_SIDE * 100.0))
    report.append("Net convention: executable return with exact two-sided fee")
    report.append("Additional slippage sensitivity: 0/5/10/20/30 bps")
    report.append("Selected entries: minimum 24h apart; primary selected N is therefore the non-overlapping sequence.")
    report.append("Short side is not scored economically unless executable short mechanics are explicitly proven.")
    report.append("All-entry baselines overlap and are NOT independent samples.")
    report.append("")
    report.append("TIME COVERAGE")
    report.append("Full signal coverage days: %.3f" % coverage_days)
    report.append("Holdout signal coverage days: %.3f" % holdout_coverage_days)
    report.append("Minimum coverage for GO: %.1f days" % MIN_COVERAGE_DAYS)
    report.append("")
    report.append("ALIGNMENT")
    delays = [x["entry_delay_sec"] for x in records]
    feature_ages = [x["feature_age_sec"] for x in records]
    report.append("Aligned signals: %d" % len(records))
    report.append("Entry delay mean/median/P90/P95/P99/max = %.6f / %.6f / %.6f / %.6f / %.6f / %.6f sec"
                  % (
                      statistics.mean(delays),
                      statistics.median(delays),
                      q(delays, .90),
                      q(delays, .95),
                      q(delays, .99),
                      max(delays),
                  ))
    report.append("Feature snapshot age mean/median/max = %.6f / %.6f / %.6f sec"
                  % (
                      statistics.mean(feature_ages),
                      statistics.median(feature_ages),
                      max(feature_ages),
                  ))
    report.append("Alignment rejected: %r" % dict(alignment_rejected))
    report.append("")
    report.append("SPLITS")
    report.append("Train N=%d" % len(train))
    report.append("Validation N=%d" % len(validation))
    report.append("Holdout N=%d" % len(holdout))
    report.append("")
    report.append("SCALING (TRAIN ONLY)")
    for name in ("obi10", "ofi_norm", "cvd_rate_60s"):
        report.append("%s mean=%.10g std=%.10g" % (name, scaling[name]["mean"], scaling[name]["std"]))
    report.append("")
    report.append("SELECTION COUNTS")
    report.append("Selected train=%d validation=%d holdout=%d before target availability filtering"
                  % (len(selected_train), len(selected_validation), len(selected_holdout)))
    report.append("Target rejects train=%r" % dict(train_reject))
    report.append("Target rejects validation=%r" % dict(validation_reject))
    report.append("Target rejects holdout=%r" % dict(holdout_reject))
    report.append("")
    report.append("selected_long_primary")
    report.append(repr(selected_long_summary))
    report.append("short_not_evaluated")
    report.append(
        "STATUS=NOT_EVALUATED: short execution mechanics are not proven in supplied data."
        if not SHORT_EXECUTION_PROVEN else repr(selected_short_summary)
    )
    report.append("baseline_all_long")
    report.append(repr(baseline_summary))
    report.append("baseline_all_short")
    report.append(
        "STATUS=NOT_EVALUATED: short execution mechanics are not proven in supplied data."
        if not SHORT_EXECUTION_PROVEN else repr(baseline_short_summary)
    )
    report.append("Selected minus baseline-all-long mean difference: %s" % improvement)
    report.append("Direction-matched baseline mean: %s" % direction_matched_baseline_mean)
    report.append("Direction-matched selected-vs-baseline mean difference: %s" % matched_improvement)
    report.append("")
    report.append("DECISION")
    report.append("STATUS=%s" % status)
    report.append("Positive selected blocks=%d/4" % positive_block_count)
    report.append("Clear improvement threshold=0.25 percentage points over direction-matched baseline.")
    report.append("Cost robust through 10 bps=%s" % cost_robust)
    report.append("Short economics status: %s" % ("EXECUTABLE" if SHORT_EXECUTION_PROVEN else "NOT_EVALUATED"))
    report.append("Sufficient selected holdout N=%s" % sufficient_sample)
    report.append("Sufficient full coverage=%s" % sufficient_coverage)
    report.append("")
    report.append("DIRECT ANSWERS")
    if holdout_positive and matched_improvement is not None and matched_improvement > 0:
        report.append("1. Selective selection changes the unconditional result directionally on the final holdout.")
    else:
        report.append("1. Selective selection does not produce a positive final-holdout economic result.")
    report.append(
        "2. Final holdout after fee + spread: %s"
        % ("POSITIVE" if holdout_positive else "NOT POSITIVE")
    )
    report.append(
        "3. Evidence sufficient to justify continuation: %s"
        % ("YES, research only" if status == "GO-FOR-FURTHER-RESEARCH" else "NO definitive evidence from this test")
    )
    if status == "INCONCLUSIVE":
        report.append("4. Current evidence is INCONCLUSIVE; additional clean data is required before a path decision.")
    elif status == "NO-GO":
        report.append("4. The selective 24h path fails the predefined economic gate; further work should not proceed on this rule.")
    else:
        report.append("4. Continue data confirmation/research; no live trading approval.")
    report.append("")
    report.append("LIMITATIONS")
    report.append("- This is a fixed-score research test, not an optimized strategy.")
    report.append("- All-entry baselines overlap; their N is descriptive, not independent.")
    report.append("- Selected entries are at least 24h apart, reducing horizon overlap but not proving statistical independence.")
    report.append("- Quote snapshots are not proof of fill size or market impact.")
    report.append("- Slippage cases are assumptions, not observed historical slippage.")
    report.append("- Short execution remains contingent on actual short mechanics; these results should not be treated as live-short approval.")
    report.append("- Positive holdout results, if any, are evidence for further research only.")

    out_csv = os.path.abspath(args.output_csv)
    out_txt = os.path.abspath(args.output_txt)
    out_dir = os.path.dirname(out_csv)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    csv_fields = [
        "section", "group", "period", "N", "mean_net", "median_net",
        "win_rate", "p25", "p75", "p90", "profit_factor",
        "cumulative_arithmetic", "compounded", "max_drawdown", "slippage_bps",
    ]
    rows_out = []

    groups = [
        ("train_selected_long_primary", [x for x in train_trades if x["side"] == "LONG"]),
        ("validation_selected_long_primary", [x for x in validation_trades if x["side"] == "LONG"]),
        (primary_group_name, primary_selected),
        ("short_not_evaluated", selected_short),
        ("holdout_all_long", baseline_holdout_long),
        ("holdout_all_short", baseline_holdout_short),
    ]
    for group_name, group_rows in groups:
        s = summary([x["net_return"] for x in group_rows])
        rows_out.append({
            "section": "summary",
            "group": group_name,
            "period": "",
            "N": s["N"],
            "mean_net": pct(s["mean"]),
            "median_net": pct(s["median"]),
            "win_rate": pct(s["win_rate"]),
            "p25": pct(s["p25"]),
            "p75": pct(s["p75"]),
            "p90": pct(s["p90"]),
            "profit_factor": s["profit_factor"],
            "cumulative_arithmetic": pct(s["cumulative_arithmetic"]),
            "compounded": pct(s["compounded"]),
            "max_drawdown": pct(s["max_drawdown"]),
            "slippage_bps": "",
        })

    rows_out.extend(block_rows)
    rows_out.extend(sensitivity)

    for row in selected_both:
        rows_out.append({
            "section": "trade",
            "group": primary_group_name,
            "period": "",
            "N": 1,
            "mean_net": pct(row["net_return"]),
            "median_net": pct(row["net_return"]),
            "win_rate": 1 if row["net_return"] > 0 else 0,
            "p25": pct(row["net_return"]),
            "p75": pct(row["net_return"]),
            "p90": pct(row["net_return"]),
            "profit_factor": "",
            "cumulative_arithmetic": pct(row["net_return"]),
            "compounded": pct(row["net_return"]),
            "max_drawdown": "",
            "slippage_bps": "",
            "entry_time": row["entry_time"],
            "exit_time": row["exit_time"],
            "side": row["side"],
            "score": row["score"],
            "gross_return": pct(row["gross_return"]),
            "trading_cost": pct(row["trading_cost"]),
            "MFE": pct(row["mfe"]),
            "MAE": pct(row["mae"]),
        })

    with open(
        out_csv, "w", newline="", encoding="utf-8"
    ) as handle:
        fields = csv_fields + [
            "entry_time", "exit_time", "side", "score",
            "gross_return", "trading_cost", "MFE", "MAE",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_out)

    with open(out_txt, "w", encoding="utf-8") as handle:
        handle.write("\n".join(report) + "\n")

    print("[OUTPUT] CSV =", out_csv)
    print("[OUTPUT] TXT =", out_txt)
    print("[RESULT] STATUS =", status)
    print("[RESULT] HOLDOUT_SELECTED_N =", holdout_summary["N"])
    print("[RESULT] HOLDOUT_SELECTED_MEAN_NET_PCT =", pct(holdout_summary["mean"]))
    print("[RESULT] HOLDOUT_SELECTED_MEDIAN_NET_PCT =", pct(holdout_summary["median"]))
    print("[RESULT] HOLDOUT_SELECTED_CUMULATIVE_PCT =", pct(holdout_summary["cumulative_arithmetic"]))
    print("[RESULT] HOLDOUT_BASELINE_ALL_LONG_MEAN_NET_PCT =", pct(baseline_summary["mean"]))
    print("[RESULT] HOLDOUT_SELECTED_MINUS_BASELINE_PCT_POINTS =", pct(improvement))


if __name__ == "__main__":
    main()

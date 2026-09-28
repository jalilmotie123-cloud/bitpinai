import csv
import io
import math
import os
import statistics
import time
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

HORIZONS = (300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400)
SLIPPAGE_BPS = (0, 5, 10, 20, 30)
FEE_SIDE = 0.0035
ALIGN_STALE_SEC = 30.0
REGIME_LOOKBACK_SEC = 300.0
MIN_RAW_N = 100
DECISION_BASE_SLIPPAGE_BPS = 20

FILES = (
    "market_data_v2.csv",
    "market_data_v3.csv",
    "matches_clean.csv",
    "tradeflow_features_v3.csv",
)
SYMBOLS = {"SOL_USDT", "SOL/USDT", "SOL-USDT", "SOLUSDT"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def local_timezone_label():
    names = getattr(time, "tzname", ("UNKNOWN", "UNKNOWN"))
    name = names[0] if names else "UNKNOWN"
    if not name:
        return "UNKNOWN"
    return str(name)


def parse_timestamp(value):
    """Return (unix_seconds_utc, interpretation_kind).

    Epoch seconds/milliseconds are always Unix UTC.
    Naive datetimes are interpreted by the host OS local-time rules via
    time.mktime(), matching the collector-host convention when the files
    came from this same local machine.
    """
    x = num(value)
    if x is not None:
        if abs(x) > 100000000000:
            return x / 1000.0, "epoch_milliseconds_utc"
        if abs(x) > 1000000000:
            return x, "epoch_seconds_utc"

    s = str(value or "").strip()
    if not s:
        return None, "missing"

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.timestamp(), "timezone_aware_datetime"
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            # time.mktime() uses the local OS timezone and DST rules.
            return time.mktime(dt.timetuple()), "naive_datetime_local"
        except ValueError:
            continue

    return None, "unparsed"


def timestamp_status(kinds):
    naive = "naive_datetime_local" in kinds
    epoch = (
        "epoch_seconds_utc" in kinds or
        "epoch_milliseconds_utc" in kinds
    )
    aware = "timezone_aware_datetime" in kinds
    if naive and local_timezone_label() == "UNKNOWN":
        return "TIMEZONE_UNCERTAIN"
    if naive and (epoch or aware):
        return "MIXED_BUT_EXPLICIT"
    if naive:
        return "LOCAL_TIMEZONE_USED"
    if epoch or aware:
        return "UTC_OR_OFFSET_EXPLICIT"
    return "TIMEZONE_UNCERTAIN"


def value(row, names):
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def read_csv(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    nul_bytes = raw.count(b"\0")
    raw = raw.replace(b"\0", b"")
    text = raw.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text))), nul_bytes


def is_sol(row):
    symbol = value(row, ("symbol", "market", "pair", "ticker"))
    if symbol is None or str(symbol).strip() == "":
        # matches_clean.csv and tradeflow_features_v3.csv are SOL-specific
        # files in this project and do not necessarily carry a symbol column.
        return True
    return str(symbol).strip().upper() in SYMBOLS


def quantile(values, p):
    vals = sorted(x for x in values if x is not None and math.isfinite(x))
    if not vals:
        return None
    pos = (len(vals) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def stats(values):
    vals = [x for x in values if x is not None and math.isfinite(x)]
    if not vals:
        return {"N": 0}
    return {
        "N": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "p10": quantile(vals, 0.10),
        "p25": quantile(vals, 0.25),
        "p50": quantile(vals, 0.50),
        "p75": quantile(vals, 0.75),
        "p90": quantile(vals, 0.90),
        "p95": quantile(vals, 0.95),
        "p99": quantile(vals, 0.99),
        "win": sum(x > 0 for x in vals) / len(vals),
    }


def format_utc(epoch):
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def audit_dataset(path):
    result = {
        "file": os.path.basename(path),
        "exists": os.path.exists(path),
        "host_local_timezone": local_timezone_label(),
    }
    if not result["exists"]:
        return result

    rows, nul_bytes = read_csv(path)
    result["rows_total"] = len(rows)
    result["nul_bytes"] = nul_bytes
    if not rows:
        result["rows_sol"] = 0
        result["timezone_status"] = "TIMEZONE_UNCERTAIN"
        return result

    keys = list(rows[0])
    time_key = next(
        (k for k in keys if k.lower() in ("time", "timestamp", "datetime", "date")),
        None,
    )
    id_key = next(
        (k for k in keys if k.lower() in ("id", "trade_id", "event_id")),
        None,
    )
    price_key = next(
        (k for k in keys if k.lower() in ("price", "last_price")),
        None,
    )
    bid_key = next((k for k in keys if k.lower() == "bid"), None)
    ask_key = next((k for k in keys if k.lower() == "ask"), None)
    symbol_key = next(
        (k for k in keys if k.lower() in ("symbol", "market", "pair", "ticker")),
        None,
    )

    sol_rows = [r for r in rows if is_sol(r)]
    result["rows_sol"] = len(sol_rows)
    result["symbol_field"] = symbol_key or "ABSENT_SOL_SPECIFIC_FILE"
    result["required_schema"] = {
        "time": time_key is not None,
        "bid": bid_key is not None,
        "ask": ask_key is not None,
        "price": price_key is not None,
        "id": id_key is not None,
    }

    original_times = []
    valid_times = []
    ids = []
    timestamp_kinds = set()
    missing_values = 0
    invalid_prices = 0
    invalid_bid_ask = 0

    for row in sol_rows:
        missing_values += sum(
            v is None or str(v).strip() == "" for v in row.values()
        )

        if time_key is not None:
            t, kind = parse_timestamp(row.get(time_key))
            timestamp_kinds.add(kind)
            if t is not None:
                original_times.append(t)
                valid_times.append(t)

        if id_key is not None and row.get(id_key):
            ids.append(str(row[id_key]).strip())

        if price_key is not None:
            p = num(row.get(price_key))
            if p is None or p <= 0:
                invalid_prices += 1

        if bid_key is not None or ask_key is not None:
            b = num(row.get(bid_key)) if bid_key is not None else None
            a = num(row.get(ask_key)) if ask_key is not None else None
            if (
                b is None or a is None or
                b <= 0 or a <= 0 or a < b
            ):
                invalid_bid_ask += 1

    sorted_times = sorted(valid_times)
    gaps = [
        b - a
        for a, b in zip(sorted_times, sorted_times[1:])
        if b >= a
    ]

    result.update(
        start=format_utc(min(sorted_times)) if sorted_times else None,
        end=format_utc(max(sorted_times)) if sorted_times else None,
        duration_sec=(max(sorted_times) - min(sorted_times)) if sorted_times else None,
        duplicate_timestamps=len(valid_times) - len(set(valid_times)),
        duplicate_ids=len(ids) - len(set(ids)),
        missing_values=missing_values,
        invalid_prices=invalid_prices,
        invalid_bid_ask=invalid_bid_ask,
        timestamp_ordering=(
            "NONDECREASING" if original_times == sorted_times else "UNORDERED"
        ),
        median_interval=statistics.median(gaps) if gaps else None,
        p90_interval=quantile(gaps, 0.90),
        p95_interval=quantile(gaps, 0.95),
        p99_interval=quantile(gaps, 0.99),
        max_gap=max(gaps) if gaps else None,
        timestamp_kinds=sorted(timestamp_kinds),
        timezone_status=timestamp_status(timestamp_kinds),
    )
    if result["timezone_status"] == "TIMEZONE_UNCERTAIN":
        result["alignment_note"] = "Alignment involving naive datetimes is uncertain."
    return result


def load_market(path):
    if not os.path.exists(path):
        return []

    rows, _ = read_csv(path)
    out = []
    for row in rows:
        if not is_sol(row):
            continue
        t, _ = parse_timestamp(value(row, ("time", "timestamp", "datetime", "date")))
        bid = num(value(row, ("bid",)))
        ask = num(value(row, ("ask",)))
        if (
            t is None or bid is None or ask is None or
            bid <= 0 or ask <= 0 or ask < bid
        ):
            continue
        mid_value = num(value(row, ("mid",)))
        mid = mid_value if mid_value is not None and mid_value > 0 else (bid + ask) / 2.0
        out.append((t, bid, ask, mid))

    out.sort(key=lambda x: x[0])
    dedup = []
    seen = set()
    for row in out:
        if row[0] in seen:
            continue
        seen.add(row[0])
        dedup.append(row)
    return dedup


def market_profile(path):
    audit = audit_dataset(path)
    market_rows = load_market(path)
    if not market_rows:
        audit["valid_executable_sol_rows"] = 0
        return audit, market_rows

    times = [x[0] for x in market_rows]
    gaps = [
        b - a for a, b in zip(times, times[1:]) if b >= a
    ]
    audit["valid_executable_sol_rows"] = len(market_rows)
    audit["valid_executable_share"] = (
        len(market_rows) / audit["rows_sol"]
        if audit.get("rows_sol") else 0.0
    )
    audit["deduped_snapshot_duplicates_removed"] = (
        len(audit.get("rows_sol", [])) if False else
        audit.get("duplicate_timestamps", 0)
    )
    audit["coverage_start_epoch"] = times[0]
    audit["coverage_end_epoch"] = times[-1]
    audit["coverage_duration_sec"] = times[-1] - times[0]
    audit["coverage_median_interval_sec"] = statistics.median(gaps) if gaps else None
    audit["coverage_p95_interval_sec"] = quantile(gaps, 0.95)
    return audit, market_rows


def choose_canonical(profiles):
    candidates = []
    for profile in profiles:
        if not profile.get("exists"):
            continue
        schema = profile.get("required_schema", {})
        executable = profile.get("valid_executable_sol_rows", 0)
        end = profile.get("coverage_end_epoch")
        if (
            schema.get("time") and schema.get("bid") and schema.get("ask") and
            executable and end is not None
        ):
            candidates.append(profile)

    if not candidates:
        return None, "No market dataset has an executable SOL time/bid/ask schema."

    # Transparent hierarchy:
    # 1) executable/schema viability
    # 2) newer temporal coverage
    # 3) longer temporal coverage
    # 4) better continuity (lower P95 interval)
    # 5) lower invalid bid/ask rate
    # 6) valid row count only as the final tie-breaker
    def key(p):
        rows = max(1, p.get("rows_sol", 0))
        invalid = p.get("invalid_bid_ask", 0) / rows
        p95 = p.get("coverage_p95_interval_sec")
        return (
            p.get("coverage_end_epoch", float("-inf")),
            p.get("coverage_duration_sec", float("-inf")),
            -float(p95 if p95 is not None else float("inf")),
            -invalid,
            p.get("valid_executable_sol_rows", 0),
        )

    selected = max(candidates, key=key)
    reason = (
        "Selected by executable/schema viability, then newest end time, "
        "then longer coverage, then continuity, invalid-rate, and only finally "
        "valid row count. Row count is not the primary selector."
    )
    return selected, reason


def align_tradeflow_signals(market, path):
    result = {
        "signals_total": 0,
        "signals_valid_time": 0,
        "aligned": 0,
        "future_market_missing": 0,
        "delayed_gt_threshold": 0,
        "delay_nonnegative": True,
        "timezone_status": "TIMEZONE_UNCERTAIN",
        "delays": [],
    }
    if not os.path.exists(path):
        return result

    rows, _ = read_csv(path)
    market_times = [x[0] for x in market]
    if not market_times:
        return result

    naive = False
    for row in rows:
        if not is_sol(row):
            continue
        result["signals_total"] += 1
        signal_time, kind = parse_timestamp(
            value(row, ("time", "timestamp", "datetime", "date"))
        )
        if kind == "naive_datetime_local":
            naive = True
        if signal_time is None:
            continue
        result["signals_valid_time"] += 1

        j = bisect_left(market_times, signal_time)
        if j >= len(market_times):
            result["future_market_missing"] += 1
            continue

        entry_snapshot_time = market_times[j]
        delay = entry_snapshot_time - signal_time
        if delay < 0:
            result["delay_nonnegative"] = False
            continue

        result["aligned"] += 1
        result["delays"].append(delay)
        if delay > ALIGN_STALE_SEC:
            result["delayed_gt_threshold"] += 1

    if naive:
        result["timezone_status"] = (
            "LOCAL_TIMEZONE_USED" if local_timezone_label() != "UNKNOWN"
            else "TIMEZONE_UNCERTAIN"
        )
    else:
        result["timezone_status"] = "UTC_OR_OFFSET_EXPLICIT"

    return result


def fixed_horizon_points(market, horizon):
    times = [x[0] for x in market]
    out = []
    for i, entry in enumerate(market):
        horizon_end = entry[0] + horizon
        j = bisect_right(times, horizon_end, i + 1) - 1
        if j <= i:
            continue

        exit_row = market[j]
        entry_mid = entry[3]
        exit_mid = exit_row[3]
        gross_mid = exit_mid / entry_mid - 1.0
        gross_after_spread = exit_row[1] / entry[2] - 1.0
        gross_after_fee = (
            exit_mid * (1.0 - FEE_SIDE) /
            (entry_mid * (1.0 + FEE_SIDE)) - 1.0
        )
        net_fee_spread = (
            exit_row[1] * (1.0 - FEE_SIDE) /
            (entry[2] * (1.0 + FEE_SIDE)) - 1.0
        )

        entry_spread = entry[2] / entry_mid - 1.0
        exit_spread = exit_mid / exit_row[1] - 1.0
        execution_factor = 1.0 + gross_after_spread
        mid_factor = 1.0 + gross_mid
        spread_drag_factor = (
            1.0 - execution_factor / mid_factor
            if mid_factor > 0 else None
        )

        out.append(
            {
                "entry_time": entry[0],
                "exit_time": exit_row[0],
                "gross_mid": gross_mid,
                "gross_after_fee": gross_after_fee,
                "gross_after_spread": gross_after_spread,
                "net_fee_spread": net_fee_spread,
                "entry_spread": entry_spread,
                "exit_spread": exit_spread,
                "spread_drag_factor": spread_drag_factor,
                "entry_ask": entry[2],
                "exit_bid": exit_row[1],
            }
        )
    return out


def future_mfe_mae(market, horizon):
    times = [x[0] for x in market]
    n = len(market)
    max_q = []
    min_q = []
    add_index = 1
    result = []

    for i in range(n):
        horizon_end = times[i] + horizon
        end_index = bisect_right(times, horizon_end, i + 1)

        while add_index < end_index:
            bid = market[add_index][1]
            while max_q and market[max_q[-1]][1] <= bid:
                max_q.pop()
            max_q.append(add_index)

            while min_q and market[min_q[-1]][1] >= bid:
                min_q.pop()
            min_q.append(add_index)
            add_index += 1

        while max_q and max_q[0] <= i:
            max_q.pop(0)
        while min_q and min_q[0] <= i:
            min_q.pop(0)

        if not max_q or not min_q:
            continue

        entry_ask = market[i][2]
        max_bid = market[max_q[0]][1]
        min_bid = market[min_q[0]][1]
        result.append(
            (
                max_bid / entry_ask - 1.0,
                min_bid / entry_ask - 1.0,
            )
        )

    return result


def realized_vol_lookback(market):
    times = [x[0] for x in market]
    mids = [x[3] for x in market]
    n = len(market)
    cumulative = [0.0]
    log_returns = [0.0]

    for i in range(1, n):
        lr = math.log(mids[i] / mids[i - 1])
        log_returns.append(lr)
        cumulative.append(cumulative[-1] + lr * lr)

    vols = [None] * n
    for i in range(1, n):
        start = bisect_left(times, times[i] - REGIME_LOOKBACK_SEC, 0, i)
        ss = cumulative[i] - cumulative[start]
        count = i - start
        if count > 0:
            vols[i] = math.sqrt(ss)
    return vols


def regime_labels(points, vols):
    valid = [v for v in vols if v is not None and math.isfinite(v)]
    q1 = quantile(valid, 1.0 / 3.0)
    q2 = quantile(valid, 2.0 / 3.0)
    labels = []
    for point in points:
        idx = point["market_index"]
        v = vols[idx] if idx < len(vols) else None
        if v is None or q1 is None or q2 is None:
            labels.append(("UNKNOWN", v))
        elif v <= q1:
            labels.append(("LOW", v))
        elif v <= q2:
            labels.append(("MEDIUM", v))
        else:
            labels.append(("HIGH", v))
    return labels, q1, q2


def block_number(t, start, end):
    width = (end - start) / 4.0
    if width <= 0:
        return 1
    return min(4, int((t - start) / width) + 1)


def write_csv(path, rows):
    fields = [
        "section", "horizon_sec", "block", "regime", "slippage_bps", "N",
        "gross_mean", "gross_median",
        "gross_after_fee_mean", "gross_after_fee_median",
        "gross_after_spread_mean", "gross_after_spread_median",
        "fee_cost_flat_pct", "entry_spread_mean_pct", "exit_spread_mean_pct",
        "spread_drag_mean_pct",
        "net_mean", "net_median", "win_rate",
        "p25", "p75", "p90", "p95",
        "gross_gt_0_25", "gross_gt_0_50", "gross_gt_0_75", "gross_gt_1_00",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def pct_or_blank(x):
    return "" if x is None else "%.8f" % (x * 100.0)


def build_row(section, horizon, block, regime, slip, points):
    gross = [p["gross_mid"] for p in points]
    after_fee = [p["gross_after_fee"] for p in points]
    after_spread = [p["gross_after_spread"] for p in points]
    fee_only_cost = 1.0 - (1.0 - FEE_SIDE) / (1.0 + FEE_SIDE)
    entry_spread = [p["entry_spread"] for p in points]
    exit_spread = [p["exit_spread"] for p in points]
    drag = [p["spread_drag_factor"] for p in points]
    net = [p["net_fee_spread"] - slip / 10000.0 for p in points]
    s = stats(net)
    return {
        "section": section,
        "horizon_sec": horizon,
        "block": block,
        "regime": regime,
        "slippage_bps": slip,
        "N": s.get("N", 0),
        "gross_mean": statistics.mean(gross) if gross else "",
        "gross_median": statistics.median(gross) if gross else "",
        "gross_after_fee_mean": statistics.mean(after_fee) if after_fee else "",
        "gross_after_fee_median": statistics.median(after_fee) if after_fee else "",
        "gross_after_spread_mean": statistics.mean(after_spread) if after_spread else "",
        "gross_after_spread_median": statistics.median(after_spread) if after_spread else "",
        "fee_cost_flat_pct": fee_only_cost * 100.0,
        "entry_spread_mean_pct": statistics.mean(entry_spread) * 100.0 if entry_spread else "",
        "exit_spread_mean_pct": statistics.mean(exit_spread) * 100.0 if exit_spread else "",
        "spread_drag_mean_pct": statistics.mean(drag) * 100.0 if drag else "",
        "net_mean": s.get("mean", ""),
        "net_median": s.get("median", ""),
        "win_rate": s.get("win", ""),
        "p25": s.get("p25", ""),
        "p75": s.get("p75", ""),
        "p90": s.get("p90", ""),
        "p95": s.get("p95", ""),
        "gross_gt_0_25": sum(x > 0.0025 for x in gross) / len(gross) if gross else "",
        "gross_gt_0_50": sum(x > 0.0050 for x in gross) / len(gross) if gross else "",
        "gross_gt_0_75": sum(x > 0.0075 for x in gross) / len(gross) if gross else "",
        "gross_gt_1_00": sum(x > 0.0100 for x in gross) / len(gross) if gross else "",
    }


def clean_number(x, digits=8):
    if x is None:
        return "N/A"
    if isinstance(x, float):
        return ("%%.%df" % digits) % x
    return str(x)


def main():
    paths = {name: os.path.join(ROOT, name) for name in FILES}
    audit_items = []
    profiles = []
    for name in ("market_data_v2.csv", "market_data_v3.csv"):
        profile, _ = market_profile(paths[name])
        profiles.append(profile)
        audit_items.append(profile)
    for name in ("matches_clean.csv", "tradeflow_features_v3.csv"):
        audit_items.append(audit_dataset(paths[name]))

    canonical_profile, selection_reason = choose_canonical(profiles)
    if canonical_profile is None:
        raise SystemExit("NO_VALID_MARKET_DATA")

    canonical_path = paths[canonical_profile["file"]]
    market = load_market(canonical_path)
    if not market:
        raise SystemExit("NO_VALID_CANONICAL_SOL_MARKET")

    report = [
        "FEASIBILITY AUDIT V1 — READ-ONLY SOL RESEARCH",
        "",
        "No ML / no strategy / no threshold sweep / no TP-SL optimization / no live execution.",
        "No input dataset is modified.",
        "",
        "TIMEZONE",
        "Host local timezone used for naive datetimes: %s" % local_timezone_label(),
        "Epoch seconds/milliseconds are interpreted as Unix UTC.",
        "Naive datetimes are interpreted by the host OS local-time rules via time.mktime().",
        "This assumes naive collector timestamps were produced in this same host local timezone.",
        "If that assumption cannot be established on the execution machine, status must be treated as TIMEZONE_UNCERTAIN.",
        "",
        "FEE MODEL",
        "fee_side=%.6f (0.35%% per side) is a configurable assumption, not verified market truth." % FEE_SIDE,
        "Exact two-sided fee-only factor = (1-fee)/(1+fee).",
        "Exact flat-price fee drag = 1-(1-fee)/(1+fee) = %.8f%%." % (
            (1.0 - (1.0 - FEE_SIDE) / (1.0 + FEE_SIDE)) * 100.0
        ),
        "",
        "CANONICAL MARKET SOURCE",
        "Selected: %s" % canonical_profile["file"],
        "Reason: %s" % selection_reason,
        "Selection does NOT use row count as the primary criterion.",
        "",
        "DATA AUDIT",
    ]

    for item in audit_items:
        report.append(repr(item))

    signals = align_tradeflow_signals(
        market, paths["tradeflow_features_v3.csv"]
    )
    delay_stats = stats(signals["delays"])
    report += [
        "",
        "CANONICAL TIMELINE",
        "signal_time = tradeflow_features_v3 timestamp when that file exists.",
        "entry_snapshot_time = first canonical market snapshot with market_time >= signal_time.",
        "entry_time is conceptually distinct from signal_time and market_snapshot_time.",
        "exit_time is the fixed-horizon future market snapshot used for the baseline.",
        "entry_snapshot_time - signal_time delay statistics: %s" % repr(delay_stats),
        "signal_time - entry_snapshot_time is the corresponding negative signed difference.",
        "Delayed/stale alignment threshold: %.1f seconds (fixed audit flag, not optimized)." % ALIGN_STALE_SEC,
        "signals_total=%d, signals_valid_time=%d, aligned=%d, future_market_missing=%d, delayed_gt_threshold=%d, delay_nonnegative=%s, timezone_status=%s"
        % (
            signals["signals_total"],
            signals["signals_valid_time"],
            signals["aligned"],
            signals["future_market_missing"],
            signals["delayed_gt_threshold"],
            signals["delay_nonnegative"],
            signals["timezone_status"],
        ),
        "",
        "SHORT",
        "SHORT = INCONCLUSIVE. Bid/ask quotes alone do not prove executable short/margin mechanics.",
        "",
        "BASELINE METHOD",
        "Every valid canonical market snapshot is an opportunity observation.",
        "Raw N is reported, but raw observations are NOT treated as independent samples.",
        "Overlapping horizons are expected to be strongly dependent, especially at 4h/6h/12h/24h.",
        "No claim of statistical proof is made from raw N alone.",
    ]

    result_rows = []
    decision_rows = []
    start_time = market[0][0]
    end_time = market[-1][0]
    vols = realized_vol_lookback(market)

    for horizon in HORIZONS:
        points = fixed_horizon_points(market, horizon)
        # attach the entry index for deterministic block/regime grouping
        for i, point in enumerate(points):
            # Fixed-horizon lookup preserves chronological order; map by exact time.
            point["market_index"] = bisect_left(
                [x[0] for x in market], point["entry_time"]
            )

        gross = [p["gross_mid"] for p in points]
        mfe_values = future_mfe_mae(market, horizon)
        mfe = [x[0] for x in mfe_values]
        mae = [x[1] for x in mfe_values]

        threshold_probs = {
            0.25: sum(x > 0.0025 for x in gross) / len(gross) if gross else None,
            0.50: sum(x > 0.0050 for x in gross) / len(gross) if gross else None,
            0.75: sum(x > 0.0075 for x in gross) / len(gross) if gross else None,
            1.00: sum(x > 0.0100 for x in gross) / len(gross) if gross else None,
        }

        report += [
            "",
            "HORIZON %ss" % horizon,
            "Baseline raw N=%d (not an independent-sample count)." % len(points),
            "A Gross only = future_mid / entry_mid - 1.",
            "B Gross after fee = future_mid*(1-fee) / (entry_mid*(1+fee)) - 1.",
            "C Gross after spread = future_bid / entry_ask - 1.",
            "D Net after fee + spread = future_bid*(1-fee) / (entry_ask*(1+fee)) - 1.",
            "E Net after additional slippage = D - slippage_bps/10000.",
            "Gross stats: %s" % repr(stats(gross)),
            "Gross probabilities > thresholds: %s" % repr(threshold_probs),
            "MFE stats: %s" % repr(stats(mfe)),
            "MAE stats: %s" % repr(stats(mae)),
            "Spread decomposition uses exact multiplicative factor drag; it is not a simple subtraction of two returns.",
        ]

        for slip in SLIPPAGE_BPS:
            result_rows.append(
                build_row("horizon", horizon, "ALL", "ALL", slip, points)
            )

        block_groups = {}
        for point in points:
            b = block_number(point["entry_time"], start_time, end_time)
            block_groups.setdefault(b, []).append(point)

        for b in range(1, 5):
            group = block_groups.get(b, [])
            for slip in SLIPPAGE_BPS:
                result_rows.append(
                    build_row("block", horizon, b, "ALL", slip, group)
                )

        regime_labels_for_points, q1, q2 = regime_labels(points, vols)
        regime_groups = {"LOW": [], "MEDIUM": [], "HIGH": [], "UNKNOWN": []}
        for point, pair in zip(points, regime_labels_for_points):
            regime_groups[pair[0]].append(point)

        report.append(
            "Regime proxy: 300s trailing realized log-return volatility; LOW/MEDIUM/HIGH are fixed empirical thirds."
        )
        report.append(
            "Regime cutpoints: q33=%s, q67=%s." % (
                clean_number(q1),
                clean_number(q2),
            )
        )
        for rg in ("LOW", "MEDIUM", "HIGH", "UNKNOWN"):
            for slip in SLIPPAGE_BPS:
                result_rows.append(
                    build_row("regime", horizon, "ALL", rg, slip, regime_groups[rg])
                )

        all_net_20 = [p["net_fee_spread"] - DECISION_BASE_SLIPPAGE_BPS / 10000.0 for p in points]
        overall_20 = stats(all_net_20)
        means_by_block = []
        block_ns = []
        for b in range(1, 5):
            group = block_groups.get(b, [])
            vals = [
                p["net_fee_spread"] - DECISION_BASE_SLIPPAGE_BPS / 10000.0
                for p in group
            ]
            ss = stats(vals)
            block_ns.append(ss.get("N", 0))
            means_by_block.append(ss.get("mean"))

        means_by_slip = {}
        for slip in SLIPPAGE_BPS:
            vals = [p["net_fee_spread"] - slip / 10000.0 for p in points]
            means_by_slip[slip] = stats(vals).get("mean")

        positive_blocks = sum(
            1 for m in means_by_block if m is not None and m > 0
        )
        enough_n = overall_20.get("N", 0) >= MIN_RAW_N
        all_blocks_positive = (
            len(means_by_block) == 4 and
            all(m is not None and m > 0 for m in means_by_block) and
            all(n > 0 for n in block_ns)
        )
        cost_stable = all(
            means_by_slip.get(slip) is not None and means_by_slip[slip] > 0
            for slip in (0, 5, 10, 20)
        )
        negative_all_blocks = (
            len(means_by_block) == 4 and
            all(m is not None and m <= 0 for m in means_by_block)
        )

        if (
            enough_n and
            overall_20.get("mean") is not None and
            overall_20["mean"] > 0 and
            all_blocks_positive and
            cost_stable
        ):
            status = "GO-FOR-FURTHER-RESEARCH"
        elif (
            enough_n and
            negative_all_blocks and
            (means_by_slip.get(20) is None or means_by_slip.get(20) <= 0)
        ):
            status = "NO-GO"
        else:
            status = "INCONCLUSIVE"

        decision_rows.append(
            (
                horizon,
                status,
                overall_20.get("N", 0),
                overall_20.get("mean"),
                overall_20.get("median"),
                means_by_slip,
                positive_blocks,
                block_ns,
                means_by_block,
            )
        )

    report += [
        "",
        "DECISION FRAMEWORK",
        "Base decision sensitivity = 20 bps additional slippage.",
        "Minimum raw N for a non-INCONCLUSIVE result = %d; raw N is not an independent-sample count." % MIN_RAW_N,
        "GO requires: raw N threshold, positive net mean at 20 bps, all four blocks positive at 20 bps, and positive mean at 0/5/10/20 bps.",
        "If only one block is positive, status cannot be GO.",
        "If positive without slippage but negative by 10-20 bps, status cannot be GO.",
        "NO-GO requires sufficient raw N and non-positive net mean in all four blocks at the 20 bps base sensitivity.",
        "All other cases are INCONCLUSIVE.",
        "These are research-gate labels, not statistical significance claims.",
        "",
        "DECISIONS BY HORIZON",
    ]

    for (
        horizon,
        status,
        n_raw,
        mean_20,
        median_20,
        means_by_slip,
        positive_blocks,
        block_ns,
        means_by_block,
    ) in decision_rows:
        report.append(
            "%ss: %s | N=%s | net_mean@20bps=%s | net_median@20bps=%s | positive_blocks=%d/4 | block_N=%s | block_means=%s | means_by_slip=%s"
            % (
                horizon,
                status,
                n_raw,
                clean_number(mean_20),
                clean_number(median_20),
                positive_blocks,
                block_ns,
                means_by_block,
                means_by_slip,
            )
        )

    report += [
        "",
        "FINAL INTERPRETATION RULES",
        "Gross opportunity is evidence that SOL can move; it is not by itself a tradable edge.",
        "Post-cost opportunity requires executable ASK-to-BID economics plus the configured fee and slippage sensitivity.",
        "Overlapping baseline observations are descriptive opportunity-density observations, not independent trades.",
        "No output is generated until this script is run locally; the audit itself does not create or modify input datasets.",
    ]

    out_dir = os.path.join(ROOT, "research")
    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, "feasibility_results.csv"), result_rows)
    with open(
        os.path.join(out_dir, "feasibility_report.txt"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()

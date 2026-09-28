import csv
import io
import math
import os
import statistics
import time
from bisect import bisect_left, bisect_right
from collections import deque
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


def local_timezone_detail():
    names = getattr(time, "tzname", ("UNKNOWN", "UNKNOWN"))
    standard = names[0] if names else "UNKNOWN"
    daylight = names[1] if len(names) > 1 else standard
    return (
        "names=%r daylight_enabled=%s standard_offset_seconds=%s daylight_offset_seconds=%s"
        % (
            names,
            bool(getattr(time, "daylight", 0)),
            getattr(time, "timezone", "UNKNOWN"),
            getattr(time, "altzone", "UNKNOWN") if getattr(time, "daylight", 0) else "N/A",
        )
    )


def local_timezone_label():
    names = getattr(time, "tzname", ("UNKNOWN", "UNKNOWN"))
    name = names[0] if names else "UNKNOWN"
    return str(name or "UNKNOWN")


def parse_timestamp(value):
    """Return (unix_seconds_utc, interpretation_kind).

    Epoch seconds/milliseconds are Unix UTC.
    Naive datetimes use the host OS local timezone via datetime.timestamp().
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

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp(), "naive_datetime_local"
        except ValueError:
            continue

    return None, "unparsed"


def timestamp_status(kinds):
    naive = "naive_datetime_local" in kinds
    explicit = (
        "epoch_seconds_utc" in kinds or
        "epoch_milliseconds_utc" in kinds or
        "timezone_aware_datetime" in kinds
    )
    if naive and local_timezone_label() == "UNKNOWN":
        return "TIMEZONE_UNCERTAIN"
    if naive and explicit:
        return "MIXED_BUT_EXPLICIT"
    if naive:
        return "LOCAL_TIMEZONE_USED"
    if explicit:
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
        # Project files matches_clean.csv and tradeflow_features_v3.csv are
        # SOL-specific and may have no symbol field.
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


def ordering_label(original_times):
    if len(original_times) < 2:
        return "INSUFFICIENT_TIMESTAMPS"
    inversions = sum(
        1 for prev, cur in zip(original_times, original_times[1:]) if cur < prev
    )
    if inversions:
        return "UNORDERED"
    if any(cur == prev for prev, cur in zip(original_times, original_times[1:])):
        return "NONDECREASING_WITH_TIES"
    return "STRICT_ASCENDING"


def audit_dataset(path):
    result = {
        "file": os.path.basename(path),
        "exists": os.path.exists(path),
        "host_local_timezone": local_timezone_label(),
        "host_local_timezone_detail": local_timezone_detail(),
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

    sol_rows = [r for r in rows if is_sol(r)]
    result["rows_sol"] = len(sol_rows)
    result["symbol_field"] = next(
        (k for k in keys if k.lower() in ("symbol", "market", "pair", "ticker")),
        None,
    ) or "ABSENT_SOL_SPECIFIC_FILE"

    result["required_schema"] = {
        "time": time_key is not None,
        "bid": bid_key is not None,
        "ask": ask_key is not None,
        "mid": any(k.lower() == "mid" for k in keys),
        "price": price_key is not None,
        "id": id_key is not None,
    }

    original_times = []
    timestamp_kinds = set()
    ids = []
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

        if id_key is not None and row.get(id_key):
            ids.append(str(row[id_key]).strip())

        if price_key is not None:
            p = num(row.get(price_key))
            if p is None or p <= 0:
                invalid_prices += 1

        if bid_key is not None and ask_key is not None:
            b = num(row.get(bid_key))
            a = num(row.get(ask_key))
            if b is None or a is None or b <= 0 or a <= 0 or a < b:
                invalid_bid_ask += 1

    sorted_times = sorted(original_times)
    unique_times = sorted(set(sorted_times))
    gaps = [
        b - a for a, b in zip(unique_times, unique_times[1:]) if b >= a
    ]
    inversion_count = sum(
        1 for prev, cur in zip(original_times, original_times[1:]) if cur < prev
    )

    result.update(
        start=format_utc(unique_times[0]) if unique_times else None,
        end=format_utc(unique_times[-1]) if unique_times else None,
        duration_sec=(unique_times[-1] - unique_times[0]) if unique_times else None,
        duplicate_timestamps=len(original_times) - len(set(original_times)),
        duplicate_ids=(
            len(ids) - len(set(ids)) if id_key is not None else "NOT_APPLICABLE"
        ),
        missing_values=missing_values,
        invalid_prices=invalid_prices if price_key is not None else "NOT_APPLICABLE",
        invalid_bid_ask=(
            invalid_bid_ask
            if bid_key is not None and ask_key is not None
            else "NOT_APPLICABLE"
        ),
        original_timestamp_ordering=ordering_label(original_times),
        original_timestamp_inversions=inversion_count,
        median_interval=statistics.median(gaps) if gaps else None,
        p90_interval=quantile(gaps, 0.90),
        p95_interval=quantile(gaps, 0.95),
        p99_interval=quantile(gaps, 0.99),
        max_gap=max(gaps) if gaps else None,
        timestamp_kinds=sorted(timestamp_kinds),
        timezone_status=timestamp_status(timestamp_kinds),
    )
    if result["timezone_status"] == "TIMEZONE_UNCERTAIN":
        result["alignment_note"] = (
            "Alignment involving naive datetimes is uncertain until the collector timezone is established."
        )
    return result


def load_market(path):
    if not os.path.exists(path):
        return []

    rows, _ = read_csv(path)
    out = []
    for row in rows:
        if not is_sol(row):
            continue
        t, _ = parse_timestamp(
            value(row, ("time", "timestamp", "datetime", "date"))
        )
        bid = num(value(row, ("bid",)))
        ask = num(value(row, ("ask",)))
        if (
            t is None or bid is None or ask is None or
            bid <= 0 or ask <= 0 or ask < bid
        ):
            continue
        mid_value = num(value(row, ("mid",)))
        mid = (
            mid_value
            if mid_value is not None and mid_value > 0
            else (bid + ask) / 2.0
        )
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
    rows_sol = audit.get("rows_sol", 0)
    valid_count = len(market_rows)
    invalid_rate = (
        audit.get("invalid_bid_ask", 0) / rows_sol
        if rows_sol and isinstance(audit.get("invalid_bid_ask"), (int, float))
        else None
    )

    schema = audit.get("required_schema", {})
    schema_score = sum(
        1 for k in ("time", "bid", "ask", "mid") if schema.get(k)
    )
    audit["valid_executable_sol_rows"] = valid_count
    audit["valid_executable_share"] = (
        valid_count / rows_sol if rows_sol else 0.0
    )
    audit["invalid_bid_ask_rate"] = invalid_rate
    audit["schema_score"] = "%d/4" % schema_score
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
        valid_share = profile.get("valid_executable_share", 0.0)
        if (
            schema.get("time") and schema.get("bid") and schema.get("ask") and
            profile.get("valid_executable_sol_rows", 0) > 0
        ):
            candidates.append(profile)

    if not candidates:
        return None, "No market dataset has an executable SOL time/bid/ask schema."

    # Deterministic hierarchy requested by the audit specification:
    # 1) executable bid/ask validity (higher valid executable share)
    # 2) usable schema (higher schema score)
    # 3) newest temporal coverage
    # 4) duration / continuity
    # 5) invalid rate
    # 6) row count as the final tie-breaker
    def key(profile):
        p95 = profile.get("coverage_p95_interval_sec")
        invalid_rate = profile.get("invalid_bid_ask_rate")
        schema = profile.get("schema_score", "0/4")
        schema_score = int(str(schema).split("/")[0])
        return (
            float(valid_share := profile.get("valid_executable_share", 0.0)),
            schema_score,
            profile.get("coverage_end_epoch", float("-inf")),
            profile.get("coverage_duration_sec", float("-inf")),
            -float(p95 if p95 is not None else float("inf")),
            -float(invalid_rate if invalid_rate is not None else float("inf")),
            profile.get("valid_executable_sol_rows", 0),
        )

    selected = max(candidates, key=key)
    reason = (
        "Hierarchy: executable SOL bid/ask validity share -> usable schema -> "
        "newest end time -> longer duration -> better continuity (lower P95 interval) -> "
        "lower invalid bid/ask rate -> row count only as final tie-breaker."
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

    kinds = set()
    for row in rows:
        if not is_sol(row):
            continue
        result["signals_total"] += 1
        signal_time, kind = parse_timestamp(
            value(row, ("time", "timestamp", "datetime", "date"))
        )
        kinds.add(kind)
        if signal_time is None:
            continue
        result["signals_valid_time"] += 1

        j = bisect_left(market_times, signal_time)
        if j < 0:
            j = 0
        if j >= len(market_times):
            result["future_market_missing"] += 1
            continue

        entry_snapshot_time = market_times[j]
        delay = entry_snapshot_time - signal_time
        if delay < -1e-9:
            result["delay_nonnegative"] = False
            continue

        result["aligned"] += 1
        result["delays"].append(max(0.0, delay))
        if delay > ALIGN_STALE_SEC:
            result["delayed_gt_threshold"] += 1

    result["timezone_status"] = timestamp_status(kinds)
    return result


def fixed_horizon_points(market, horizon):
    times = [x[0] for x in market]
    out = []
    j = 1
    n_market = len(market)

    for i, entry in enumerate(market):
        if j < i + 1:
            j = i + 1
        horizon_end = entry[0] + horizon
        while j + 1 < n_market and times[j + 1] <= horizon_end:
            j += 1
        if j >= n_market or j <= i:
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
        mid_factor = 1.0 + gross_mid
        execution_factor = 1.0 + gross_after_spread
        spread_drag_factor = (
            1.0 - execution_factor / mid_factor
            if mid_factor > 0 else None
        )

        out.append(
            {
                "market_index": i,
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


def future_mfe_mae_bruteforce(market, horizon):
    """Reference implementation used only by the internal self-check."""
    times = [x[0] for x in market]
    result = []
    for i, entry in enumerate(market):
        horizon_end = entry[0] + horizon
        j = bisect_right(times, horizon_end, i + 1) - 1
        if j <= i:
            continue
        max_bid = max(x[1] for x in market[i + 1:j + 1])
        min_bid = min(x[1] for x in market[i + 1:j + 1])
        result.append(
            (
                max_bid / entry[2] - 1.0,
                min_bid / entry[2] - 1.0,
            )
        )
    return result


def future_mfe_mae(market, horizon):
    """O(N) sliding-window MFE/MAE using monotonic deques."""
    times = [x[0] for x in market]
    max_q = deque()
    min_q = deque()
    right = 1
    n_market = len(market)
    result = []

    for i, entry in enumerate(market):
        if right < i + 1:
            right = i + 1

        horizon_end = entry[0] + horizon
        while right < n_market and times[right] <= horizon_end:
            bid = market[right][1]

            while max_q and market[max_q[-1]][1] <= bid:
                max_q.pop()
            max_q.append(right)

            while min_q and market[min_q[-1]][1] >= bid:
                min_q.pop()
            min_q.append(right)
            right += 1

        while max_q and max_q[0] <= i:
            max_q.popleft()
        while min_q and min_q[0] <= i:
            min_q.popleft()

        if not max_q or not min_q:
            continue

        entry_ask = entry[2]
        max_bid = market[max_q[0]][1]
        min_bid = market[min_q[0]][1]
        result.append(
            (
                max_bid / entry_ask - 1.0,
                min_bid / entry_ask - 1.0,
            )
        )

    return result


def self_check_mfe_mae():
    synthetic = [
        (0.0, 100.0, 101.0, 100.5),
        (1.0, 103.0, 104.0, 103.5),
        (2.0, 99.0, 100.0, 99.5),
        (5.0, 110.0, 111.0, 110.5),
        (6.0, 98.0, 99.0, 98.5),
    ]
    for horizon in (1.0, 3.0, 6.0):
        ref = future_mfe_mae_bruteforce(synthetic, horizon)
        fast = future_mfe_mae(synthetic, horizon)
        if len(ref) != len(fast):
            raise RuntimeError("MFE_MAE_SELF_CHECK_LENGTH_FAILED")
        for left, right in zip(ref, fast):
            if not (
                math.isclose(left[0], right[0], rel_tol=1e-12, abs_tol=1e-12)
                and math.isclose(left[1], right[1], rel_tol=1e-12, abs_tol=1e-12)
            ):
                raise RuntimeError(
                    "MFE_MAE_SELF_CHECK_VALUE_FAILED: horizon=%s ref=%r fast=%r"
                    % (horizon, left, right)
                )


def realized_vol_lookback(market):
    times = [x[0] for x in market]
    mids = [x[3] for x in market]
    n_market = len(market)

    cumulative_sq = [0.0]
    for i in range(1, n_market):
        lr = math.log(mids[i] / mids[i - 1])
        cumulative_sq.append(cumulative_sq[-1] + lr * lr)

    vols = [None] * n_market
    start = 1
    for i in range(1, n_market):
        cutoff = times[i] - REGIME_LOOKBACK_SEC
        if start > i:
            start = i
        while start < i and times[start] < cutoff:
            start += 1
        first_return_index = max(1, start)
        count = i - first_return_index + 1
        if count > 0:
            ss = cumulative_sq[i] - cumulative_sq[first_return_index - 1]
            vols[i] = math.sqrt(ss)
    return vols


def build_regime_labels(market, vols):
    """Classify each entry using thirds learned only from the immediately
    preceding chronological block. First block has no prior information and
    remains UNKNOWN in regime reporting.
    """
    if not market:
        return [], {}

    start_time = market[0][0]
    end_time = market[-1][0]
    block_values = {1: [], 2: [], 3: [], 4: []}

    for i, row in enumerate(market):
        if vols[i] is None:
            continue
        b = block_number(row[0], start_time, end_time)
        block_values[b].append(vols[i])

    labels = ["UNKNOWN"] * len(market)
    cutpoints = {}

    for b in range(2, 5):
        calibration = block_values[b - 1]
        q1 = quantile(calibration, 1.0 / 3.0)
        q2 = quantile(calibration, 2.0 / 3.0)
        cutpoints[b] = (q1, q2)
        if q1 is None or q2 is None:
            continue

        for i, row in enumerate(market):
            if block_number(row[0], start_time, end_time) != b:
                continue
            v = vols[i]
            if v is None:
                continue
            if v <= q1:
                labels[i] = "LOW"
            elif v <= q2:
                labels[i] = "MEDIUM"
            else:
                labels[i] = "HIGH"

    return labels, cutpoints


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


def clean_number(x, digits=8):
    if x is None:
        return "N/A"
    if isinstance(x, float):
        return ("%%.%df" % digits) % x
    return str(x)


def main():
    print("FEASIBILITY AUDIT V1 — READ-ONLY SOL RESEARCH")
    print("[SELF-CHECK] MFE/MAE reference vs monotonic-deque")
    self_check_mfe_mae()
    print("[SELF-CHECK] MFE/MAE PASS")

    paths = {name: os.path.join(ROOT, name) for name in FILES}

    print("[DATASET] loading and auditing inputs")
    audit_items = []
    profiles = []

    for name in ("market_data_v2.csv", "market_data_v3.csv"):
        print("[DATASET] %s" % name)
        profile, _ = market_profile(paths[name])
        profiles.append(profile)
        audit_items.append(profile)

    for name in ("matches_clean.csv", "tradeflow_features_v3.csv"):
        print("[DATASET] %s" % name)
        audit_items.append(audit_dataset(paths[name]))

    canonical_profile, selection_reason = choose_canonical(profiles)
    if canonical_profile is None:
        raise SystemExit("NO_VALID_MARKET_DATA")

    canonical_path = paths[canonical_profile["file"]]
    print(
        "[CANONICAL] %s | %d valid executable SOL snapshots"
        % (canonical_profile["file"], canonical_profile["valid_executable_sol_rows"])
    )

    market = load_market(canonical_path)
    if not market:
        raise SystemExit("NO_VALID_CANONICAL_SOL_MARKET")

    signals = align_tradeflow_signals(
        market, paths["tradeflow_features_v3.csv"]
    )
    delay_stats = stats(signals["delays"])

    report = [
        "FEASIBILITY AUDIT V1 — READ-ONLY SOL RESEARCH",
        "",
        "No ML / no strategy / no threshold sweep / no TP-SL optimization / no live execution.",
        "No input dataset is modified.",
        "",
        "TIMEZONE",
        "Host local timezone: %s" % local_timezone_label(),
        "Host local timezone detail: %s" % local_timezone_detail(),
        "Epoch seconds/milliseconds are interpreted as Unix UTC.",
        "Timezone-aware datetimes use their embedded offset.",
        "Naive datetimes are interpreted by the host OS local timezone via datetime.timestamp().",
        "This assumes naive collector timestamps were produced in this same host local timezone.",
        "If that assumption cannot be established, alignment must be treated as TIMEZONE_UNCERTAIN.",
        "",
        "FEE MODEL",
        "fee_side=%.6f (0.35%% per side) is a configurable assumption, not verified market truth." % FEE_SIDE,
        "Exact two-sided fee-only factor = (1-fee)/(1+fee).",
        "Exact flat-price fee drag = 1-(1-fee)/(1+fee) = %.8f%%." % (
            (1.0 - (1.0 - FEE_SIDE) / (1.0 + FEE_SIDE)) * 100.0
        ),
        "",
        "CANONICAL MARKET SOURCE",
        "CANONICAL_SOURCE=%s" % canonical_profile["file"],
        "SELECTION_REASON=%s" % selection_reason,
        "",
        "DATA AUDIT",
    ]

    for item in audit_items:
        report.append(repr(item))

    report += [
        "",
        "CANONICAL TIMELINE",
        "signal_time = tradeflow_features_v3 timestamp when present.",
        "market_snapshot_time = canonical market snapshot used for alignment.",
        "entry_snapshot_time = first canonical market snapshot with market_time >= signal_time.",
        "entry_time is conceptually distinct from signal_time.",
        "exit_time = last canonical market snapshot at or before signal_time + horizon for the fixed-horizon baseline.",
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
        "Raw N is reported, but raw observations are NOT independent samples.",
        "Overlapping horizons can be strongly dependent, especially at 4h/6h/12h/24h.",
        "No statistical-proof claim is made from raw N alone.",
    ]

    result_rows = []
    decision_rows = []
    start_time = market[0][0]
    end_time = market[-1][0]

    print("[REGIME] computing trailing realized volatility")
    vols = realized_vol_lookback(market)
    regime_labels, regime_cutpoints = build_regime_labels(market, vols)

    for horizon_index, horizon in enumerate(HORIZONS, 1):
        print(
            "[%d/%d] HORIZON=%ss START"
            % (horizon_index, len(HORIZONS), horizon)
        )

        points = fixed_horizon_points(market, horizon)
        gross = [p["gross_mid"] for p in points]

        mfe_values = future_mfe_mae(market, horizon)
        mfe = [x[0] for x in mfe_values]
        mae = [x[1] for x in mfe_values]
        print(
            "[%d/%d] HORIZON=%ss MFE/MAE DONE N=%d"
            % (horizon_index, len(HORIZONS), horizon, len(mfe_values))
        )

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
            "Spread decomposition is factor-based and is not a simple subtraction of returns.",
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

        regime_groups = {"LOW": [], "MEDIUM": [], "HIGH": []}
        unknown_regime = 0
        for point in points:
            rg = regime_labels[point["market_index"]]
            if rg in regime_groups:
                regime_groups[rg].append(point)
            else:
                unknown_regime += 1

        report.append(
            "Regime = trailing 300s realized log-return volatility. "
            "For each block after block 1, LOW/MEDIUM/HIGH empirical thirds are calibrated only "
            "from the immediately preceding block; block 1 is UNKNOWN because no prior data exists."
        )
        for b in range(2, 5):
            qcuts = regime_cutpoints.get(b, (None, None))
            report.append(
                "Regime cutpoints for block %d from prior block: q33=%s, q67=%s."
                % (b, clean_number(qcuts[0]), clean_number(qcuts[1]))
            )
        report.append(
            "Unclassified first-block regime observations at this horizon: %d."
            % unknown_regime
        )

        for rg in ("LOW", "MEDIUM", "HIGH"):
            for slip in SLIPPAGE_BPS:
                result_rows.append(
                    build_row("regime", horizon, "ALL", rg, slip, regime_groups[rg])
                )

        all_net_20 = [
            p["net_fee_spread"] - DECISION_BASE_SLIPPAGE_BPS / 10000.0
            for p in points
        ]
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

        print(
            "[%d/%d] HORIZON=%ss DONE N=%d"
            % (horizon_index, len(HORIZONS), horizon, len(points))
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
        "No statistical-proof claim is made from overlapping raw N alone.",
        "No output is produced until the script is run locally; this repository change does not create result CSV/report files.",
    ]

    out_dir = os.path.join(ROOT, "research")
    os.makedirs(out_dir, exist_ok=True)
    print("[OUTPUT] writing research/feasibility_results.csv")
    write_csv(os.path.join(out_dir, "feasibility_results.csv"), result_rows)
    print("[OUTPUT] writing research/feasibility_report.txt")
    with open(
        os.path.join(out_dir, "feasibility_report.txt"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write("\n".join(report) + "\n")
    print("[OUTPUT] complete")


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


if __name__ == "__main__":
    main()

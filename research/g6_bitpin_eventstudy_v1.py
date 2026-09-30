# -*- coding: utf-8 -*-
"""
BitpinAI - OCT24 G6 -> Bitpin SOL event study v1
Python 3.8 / Windows 7 compatible.
READ-ONLY: does not modify input datasets.

Purpose
-------
Test whether OCT24 G6 signal timestamps coincide with unusually large
future SOL moves on Bitpin, without assuming that Gold/Silver means Long/Short.

Important
---------
The observed G6 API records contain:
id, signalType, presetName, winRate, tpPercent, lcPercent, openedAt, resultType

No explicit trade direction was observed. Therefore this script DOES NOT
convert Gold/Silver to Long/Short and does not compute directional trading PnL.

Inputs under D:\BitpinAI:
- data\\g6\\live\\g6_signals_*.jsonl
- market_data_v3.csv (preferred) or market_data_v2.csv

Outputs:
- research\\g6_bitpin_eventstudy_v1.csv
- research\\g6_bitpin_eventstudy_v1_report.txt

Horizon set is fixed:
5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 24h

For each G6 signal in the time overlap with Bitpin SOL market data:
- select the first Bitpin SOL snapshot at/after openedAt
- measure delay from signal to market snapshot
- compute absolute future mid move
- compute signed future mid return separately, but DO NOT treat it as
  trade direction
- compare G6 event windows with a deterministic baseline built from every
  eligible Bitpin SOL market timestamp in the same overlap

No ML, threshold optimization, random sampling, or resultType leakage.
"""

import csv
import glob
import math
import os
import statistics
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
G6_DIR = os.path.join(ROOT, "data", "g6", "live")
MARKET_CANDIDATES = [
    os.path.join(ROOT, "market_data_v3.csv"),
    os.path.join(ROOT, "market_data_v2.csv"),
]
OUT_CSV = os.path.join(ROOT, "research", "g6_bitpin_eventstudy_v1.csv")
OUT_REPORT = os.path.join(ROOT, "research", "g6_bitpin_eventstudy_v1_report.txt")
SYMBOL = "SOL_USDT"
HORIZONS = (300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400)


def parse_time(value):
    s = str(value).strip()
    try:
        x = float(s)
        # Heuristic only for numeric timestamps: seconds vs milliseconds.
        if x > 100000000000:
            x /= 1000.0
        return x
    except ValueError:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def pct(a, b):
    if b <= 0 or not math.isfinite(a) or not math.isfinite(b):
        return float("nan")
    return (a / b - 1.0) * 100.0


def choose_market_file():
    for path in MARKET_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "Neither market_data_v3.csv nor market_data_v2.csv exists in D:\BitpinAI"
    )


def load_g6():
    paths = sorted(glob.glob(os.path.join(G6_DIR, "g6_signals_*.jsonl")))
    if not paths:
        raise FileNotFoundError("No G6 JSONL chunks found under data\\g6\\live")

    rows = []
    seen = set()
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = __import__("json").loads(line)
                except Exception:
                    continue
                sid = obj.get("id")
                opened = obj.get("openedAt")
                if sid is None or not opened:
                    continue
                key = str(sid)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    ts = parse_time(opened)
                except Exception:
                    continue
                rows.append({
                    "id": key,
                    "ts": ts,
                    "signalType": str(obj.get("signalType", "")),
                    "presetName": str(obj.get("presetName", "")),
                    "winRate": obj.get("winRate", ""),
                    "tpPercent": obj.get("tpPercent", ""),
                    "lcPercent": obj.get("lcPercent", ""),
                    # resultType is retained only for descriptive reporting;
                    # NEVER used as a predictor because it is a future outcome.
                    "resultType": str(obj.get("resultType", "")),
                })
    rows.sort(key=lambda x: (x["ts"], x["id"]))
    return rows


def load_market(path):
    rows = []
    nul_count = 0

    def clean_lines(fh):
        nonlocal nul_count
        for line in fh:
            n = line.count("\x00")
            if n:
                nul_count += n
                line = line.replace("\x00", "")
            yield line

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(clean_lines(fh))
        fields = set(r.fieldnames or [])
        needed = {"time", "symbol", "bid", "ask", "mid"}
        if not needed.issubset(fields):
            raise ValueError(
                "market file must contain at least: time,symbol,bid,ask,mid"
            )
        for x in r:
            if str(x.get("symbol", "")).strip() != SYMBOL:
                continue
            try:
                ts = parse_time(x["time"])
                bid = float(x["bid"])
                ask = float(x["ask"])
                mid = float(x["mid"])
            except Exception:
                continue
            if not all(math.isfinite(v) for v in (ts, bid, ask, mid)):
                continue
            if bid <= 0 or ask <= 0 or mid <= 0:
                continue
            rows.append((ts, bid, ask, mid))
    rows.sort(key=lambda z: z[0])
    return rows, nul_count


def sample_stats(values):
    v = [x for x in values if math.isfinite(x)]
    if not v:
        return {"n": 0, "mean": float("nan"), "median": float("nan")}
    return {"n": len(v), "mean": statistics.mean(v), "median": statistics.median(v)}


def main():
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    market_file = choose_market_file()
    g6 = load_g6()
    market, nul_count = load_market(market_file)

    if not g6:
        raise ValueError("No usable G6 records.")
    if not market:
        raise ValueError("No usable SOL market rows.")

    mt = [x[0] for x in market]
    g6_start, g6_end = g6[0]["ts"], g6[-1]["ts"]
    m_start, m_end = market[0][0], market[-1][0]
    overlap_start = max(g6_start, m_start)
    overlap_end = min(g6_end, m_end)

    events = []
    delay = []
    signal_types = {}

    for s in g6:
        if s["ts"] < overlap_start or s["ts"] > overlap_end:
            continue
        k = bisect_left(mt, s["ts"])
        if k >= len(market):
            continue
        snap = market[k]
        delay_s = snap[0] - s["ts"]
        delay.append(delay_s)
        signal_types[s["signalType"]] = signal_types.get(s["signalType"], 0) + 1

        row = {
            "g6_id": s["id"],
            "signal_ts": s["ts"],
            "signalType": s["signalType"],
            "presetName": s["presetName"],
            "market_ts": snap[0],
            "alignment_delay_s": delay_s,
            "entry_mid": snap[3],
            "entry_ask": snap[2],
            "entry_bid": snap[1],
        }

        for h in HORIZONS:
            target = s["ts"] + h
            k2 = bisect_left(mt, target)
            if k2 >= len(market):
                row["signed_%ss" % h] = float("nan")
                row["abs_%ss" % h] = float("nan")
                continue
            future_mid = market[k2][3]
            r = pct(future_mid, snap[3])
            row["signed_%ss" % h] = r
            row["abs_%ss" % h] = abs(r)

        events.append(row)

    if not events:
        raise ValueError("No G6/Bitpin SOL time overlap.")
    
    # Deterministic baseline: all Bitpin SOL market timestamps in the overlap
    # for which a future horizon endpoint exists. This is not a trading strategy;
    # it measures whether G6 timestamps are associated with larger moves than
    # ordinary market timestamps from the same period.
    baseline_indices = []
    start_k = bisect_left(mt, overlap_start)
    end_k = bisect_right(mt, overlap_end)
    for k in range(start_k, end_k):
        baseline_indices.append(k)

    baseline = {h: [] for h in HORIZONS}
    for k in baseline_indices:
        ts, bid, ask, mid = market[k]
        for h in HORIZONS:
            k2 = bisect_left(mt, ts + h)
            if k2 >= len(market):
                continue
            future = market[k2][3]
            rr = pct(future, mid)
            if math.isfinite(rr):
                baseline[h].append(abs(rr))

    fieldnames = list(events[0].keys())
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in events:
            w.writerow(row)

    lines = []
    lines.append("BITPINAI - OCT24 G6 -> BITPIN SOL EVENT STUDY V1")
    lines.append("=" * 68)
    lines.append("G6 records loaded: %d" % len(g6))
    lines.append("Bitpin SOL rows loaded: %d" % len(market))
    lines.append("NUL bytes removed while reading market file: %d" % nul_count)
    lines.append("G6 time range UTC: %s -> %s" % (
        datetime.fromtimestamp(g6_start, timezone.utc).isoformat(),
        datetime.fromtimestamp(g6_end, timezone.utc).isoformat(),
    ))
    lines.append("Bitpin time range UTC: %s -> %s" % (
        datetime.fromtimestamp(m_start, timezone.utc).isoformat(),
        datetime.fromtimestamp(m_end, timezone.utc).isoformat(),
    ))
    lines.append("Overlap UTC: %s -> %s" % (
        datetime.fromtimestamp(overlap_start, timezone.utc).isoformat(),
        datetime.fromtimestamp(overlap_end, timezone.utc).isoformat(),
    ))
    lines.append("Aligned G6 events: %d" % len(events))
    ds = sample_stats(delay)
    lines.append(
        "Signal->market alignment delay: n=%d mean=%.3fs median=%.3fs"
        % (ds["n"], ds["mean"], ds["median"])
    )
    lines.append("SignalType counts: %s" % signal_types)
    lines.append("")
    lines.append("IMPORTANT: G6 direction was NOT assumed from Gold/Silver.")
    lines.append("resultType is descriptive only and is NOT used as a predictor.")
    lines.append("")

    for h in HORIZONS:
        vals = [e["abs_%ss" % h] for e in events if math.isfinite(e["abs_%ss" % h])]
        st = sample_stats(vals)
        b = sample_stats(baseline[h])
        diff = (
            st["mean"] - b["mean"]
            if math.isfinite(st["mean"]) and math.isfinite(b["mean"])
            else float("nan")
        )
        lines.append(
            "H=%ss | G6 n=%d mean_abs=%.5f%% median_abs=%.5f%% | "
            "Baseline n=%d mean_abs=%.5f%% | Difference=%+.5f%%"
            % (
                h, st["n"], st["mean"], st["median"],
                b["n"], b["mean"], diff
            )
        )

    lines.append("")
    lines.append("Directional trading conclusion: INCONCLUSIVE until G6 direction is identified.")
    lines.append("Opportunity-timing conclusion: use the event-study numbers above;")
    lines.append("positive excess absolute movement would support G6 as a timing/context signal,")
    lines.append("but would NOT by itself establish profitable Bitpin trading.")
    
    with open(OUT_REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("G6_RECORDS=", len(g6))
    print("BITPIN_SOL_ROWS=", len(market))
    print("NUL_BYTES_REMOVED=", nul_count)
    print("OVERLAP_EVENTS=", len(events))
    print("ALIGNMENT_MEDIAN_SEC=%.3f" % ds["median"])
    print("MARKET_FILE=", market_file)
    print("REPORT=", OUT_REPORT)
    print("CSV=", OUT_CSV)


if __name__ == "__main__":
    main()

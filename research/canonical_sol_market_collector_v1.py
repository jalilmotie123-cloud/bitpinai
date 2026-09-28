# -*- coding: utf-8 -*-
"""
Canonical SOL market collector v1.

Read-only with respect to Bitpin: this process only requests public orderbook
snapshots and writes NEW local canonical data files owned by this collector.
It never places orders.
"""

import argparse
import csv
import datetime
import os
import signal
import time

import requests


DEFAULT_URL_TEMPLATE = "https://api.bitpin.org/api/v1/mth/orderbook/{symbol}/"
SYMBOL = "SOL_USDT"
DEFAULT_OUTPUT = "canonical_sol_market_v1.csv"
DEFAULT_INTERVAL_SEC = 2.0
DEFAULT_TIMEOUT_SEC = 10.0
MAX_STATE_GAP_SEC = 10.0
GAP_WARNING_SEC = 10.0
GAP_OUTAGE_SEC = 60.0

HEADER = [
    "request_sent_at_epoch_ms",
    "received_at_epoch_ms",
    "request_sent_at_iso",
    "received_at_iso",
    "response_latency_ms",
    "symbol",
    "server_timestamp_available",
    "server_timestamp_epoch_ms",
    "server_timestamp_iso",
    "bid",
    "ask",
    "mid",
    "spread_pct",
    "bid_vol1",
    "ask_vol1",
    "bid3",
    "ask3",
    "bid5",
    "ask5",
    "bid10",
    "ask10",
    "obi1",
    "obi3",
    "obi5",
    "obi10",
    "ofi_raw",
    "ofi_norm",
    "gap_sec",
    "continuity_flag",
    "state_reset",
    "session_id",
    "reconnect_count",
]


def now_epoch_ms():
    return int(time.time() * 1000.0)


def now_local_iso(epoch_ms=None):
    if epoch_ms is None:
        epoch_ms = now_epoch_ms()
    dt = datetime.datetime.fromtimestamp(
        epoch_ms / 1000.0
    ).astimezone()
    return dt.isoformat(timespec="milliseconds")


def parse_timestamp(value):
    """Compatibility helper: parse Unix seconds/milliseconds or ISO datetime."""
    try:
        x = float(value)
        if abs(x) > 100000000000:
            return x / 1000.0, "epoch_milliseconds_utc"
        if abs(x) > 1000000000:
            return x, "epoch_seconds_utc"
    except (TypeError, ValueError):
        pass

    text = str(value or "").strip()
    if not text:
        return None, "missing"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            return dt.timestamp(), "timezone_aware_datetime"
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.datetime.strptime(text, fmt)
            return dt.timestamp(), "naive_datetime_local"
        except ValueError:
            continue
    return None, "unparsed"


def finite_float(value):
    try:
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return None
        return x
    except (TypeError, ValueError):
        return None


def depth_sum(levels, count):
    total = 0.0
    for level in levels[:count]:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        amount = finite_float(level[1])
        if amount is not None and amount >= 0:
            total += amount
    return total


def calculate_obi(bid_volume, ask_volume):
    total = bid_volume + ask_volume
    if total <= 0:
        return 0.0
    return (bid_volume - ask_volume) / total


def calculate_ofi(
    previous_bid,
    current_bid,
    previous_bid_volume,
    current_bid_volume,
    previous_ask,
    current_ask,
    previous_ask_volume,
    current_ask_volume,
):
    bid_term = 0.0
    ask_term = 0.0

    if current_bid > previous_bid:
        bid_term = current_bid_volume
    elif current_bid < previous_bid:
        bid_term = -previous_bid_volume
    else:
        bid_term = current_bid_volume - previous_bid_volume

    if current_ask < previous_ask:
        ask_term = current_ask_volume
    elif current_ask > previous_ask:
        ask_term = -previous_ask_volume
    else:
        ask_term = current_ask_volume - previous_ask_volume

    return bid_term + ask_term


def classify_gap(gap_sec):
    if gap_sec is None:
        return "normal"
    if gap_sec <= GAP_WARNING_SEC:
        return "normal"
    if gap_sec <= GAP_OUTAGE_SEC:
        return "warning"
    return "outage"


def repair_trailing_partial_line(path):
    """Repair a torn final CSV line in a file owned by this collector.

    Only the trailing incomplete record is removed. Existing complete rows are
    preserved. This function is never called for legacy project datasets.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False

    with open(path, "rb+") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            return False
        handle.seek(-1, os.SEEK_END)
        if handle.read(1) in (b"\n", b"\r"):
            return False

        chunk_size = 4096
        position = max(0, size - chunk_size)
        handle.seek(position)
        tail = handle.read(size - position)
        last_newline = max(tail.rfind(b"\n"), tail.rfind(b"\r"))
        if last_newline < 0:
            # Leave a file with only its header intact; if there is no newline
            # at all it is safer to refuse truncation than guess.
            return False

        truncate_at = position + last_newline + 1
        handle.truncate(truncate_at)
        handle.flush()
        os.fsync(handle.fileno())
        return True


class AtomicCSVAppender(object):
    def __init__(self, path, header):
        self.path = path
        self.header = header
        repaired = repair_trailing_partial_line(path)
        if repaired:
            print("[RECOVERY] truncated incomplete trailing CSV record:", path)
        self._ensure_header()

    def _ensure_header(self):
        if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            with open(self.path, "rb") as handle:
                first_line = handle.readline().rstrip(b"\r\n").decode("utf-8", errors="replace")
            expected = ",".join(self.header)
            if first_line != expected:
                raise RuntimeError(
                    "CANONICAL_CSV_HEADER_MISMATCH: %s" % self.path
                )
            return
        with open(self.path, "ab") as handle:
            line = (",".join(self.header) + "\r\n").encode("utf-8")
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def append(self, values):
        line_buffer = io_bytes_csv(values)
        with open(self.path, "ab") as handle:
            handle.write(line_buffer)
            handle.flush()
            os.fsync(handle.fileno())


def io_bytes_csv(values):
    import io
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\r\n")
    writer.writerow(values)
    return text.getvalue().encode("utf-8")


def parse_server_timestamp(data):
    for key in ("timestamp", "server_timestamp", "ts", "time"):
        if key not in data:
            continue
        value = data.get(key)
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if x > 100000000000:
            return int(x), "numeric_epoch_ms"
        if x > 1000000000:
            return int(x * 1000.0), "numeric_epoch_s"
    return None, None


def extract_snapshot(data):
    bids = data.get("bids") or []
    asks = data.get("asks") or []
    if not bids or not asks:
        raise ValueError("empty orderbook")

    bid = finite_float(bids[0][0])
    ask = finite_float(asks[0][0])
    bid_vol1 = finite_float(bids[0][1])
    ask_vol1 = finite_float(asks[0][1])

    if (
        bid is None or ask is None or
        bid_vol1 is None or ask_vol1 is None or
        bid <= 0 or ask <= 0 or ask < bid or
        bid_vol1 < 0 or ask_vol1 < 0
    ):
        raise ValueError("invalid best bid/ask")

    mid = (bid + ask) / 2.0
    spread_pct = ((ask / bid) - 1.0) * 100.0

    bid3 = depth_sum(bids, 3)
    ask3 = depth_sum(asks, 3)
    bid5 = depth_sum(bids, 5)
    ask5 = depth_sum(asks, 5)
    bid10 = depth_sum(bids, 10)
    ask10 = depth_sum(asks, 10)

    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "bid_vol1": bid_vol1,
        "ask_vol1": ask_vol1,
        "bid3": bid3,
        "ask3": ask3,
        "bid5": bid5,
        "ask5": ask5,
        "bid10": bid10,
        "ask10": ask10,
        "obi1": calculate_obi(bid_vol1, ask_vol1),
        "obi3": calculate_obi(bid3, ask3),
        "obi5": calculate_obi(bid5, ask5),
        "obi10": calculate_obi(bid10, ask10),
    }


def build_record(snapshot, request_ms, received_ms, previous, max_state_gap):
    gap_sec = None
    continuity_flag = "normal"
    state_reset = 0
    ofi_raw = 0.0
    ofi_norm = 0.0

    if previous is None:
        continuity_flag = "normal"
        state_reset = 1
    else:
        gap_sec = (received_ms - previous["received_ms"]) / 1000.0
        continuity_flag = classify_gap(gap_sec)
        if gap_sec > max_state_gap:
            state_reset = 1

        if state_reset:
            ofi_raw = 0.0
            ofi_norm = 0.0
        else:
            ofi_raw = calculate_ofi(
                previous["bid"],
                snapshot["bid"],
                previous["bid_vol1"],
                snapshot["bid_vol1"],
                previous["ask"],
                snapshot["ask"],
                previous["ask_vol1"],
                snapshot["ask_vol1"],
            )
            depth10 = snapshot["bid10"] + snapshot["ask10"]
            if depth10 > 0:
                ofi_norm = ofi_raw / depth10

    server_timestamp_epoch_ms = snapshot.get("server_timestamp_epoch_ms")

    return [
        request_ms,
        received_ms,
        now_local_iso(request_ms),
        now_local_iso(received_ms),
        received_ms - request_ms,
        SYMBOL,
        bool(snapshot.get("server_timestamp_available")),
        server_timestamp_epoch_ms,
        (
            datetime.datetime.fromtimestamp(
                server_timestamp_epoch_ms / 1000.0, timezone.utc
            ).isoformat()
            if server_timestamp_epoch_ms is not None
            else ""
        ),
        snapshot["bid"],
        snapshot["ask"],
        snapshot["mid"],
        snapshot["spread_pct"],
        snapshot["bid_vol1"],
        snapshot["ask_vol1"],
        snapshot["bid3"],
        snapshot["ask3"],
        snapshot["bid5"],
        snapshot["ask5"],
        snapshot["bid10"],
        snapshot["ask10"],
        snapshot["obi1"],
        snapshot["obi3"],
        snapshot["obi5"],
        snapshot["obi10"],
        ofi_raw,
        ofi_norm,
        gap_sec,
        continuity_flag,
        state_reset,
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Canonical SOL-only Bitpin orderbook collector v1."
    )
    parser.add_argument(
        "--url-template",
        default=DEFAULT_URL_TEMPLATE,
        help="URL template containing {symbol}.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Collector-owned CSV output path.",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=DEFAULT_INTERVAL_SEC,
        help="Target request-start cadence. Default: 2 seconds.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=DEFAULT_TIMEOUT_SEC,
        help="HTTP timeout.",
    )
    parser.add_argument(
        "--max-state-gap-sec",
        type=float,
        default=MAX_STATE_GAP_SEC,
        help="Reset OFI state when received-at gap exceeds this value.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch one snapshot and stop.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.interval_sec <= 0:
        raise SystemExit("interval-sec must be positive")
    if args.max_state_gap_sec < 0:
        raise SystemExit("max-state-gap-sec must be non-negative")

    output_path = os.path.abspath(args.output)
    session_id = "%d-%d" % (os.getpid(), now_epoch_ms())
    reconnect_count = 0
    had_failure = False
    previous = None
    stop_requested = [False]

    def request_stop(signum, frame):
        stop_requested[0] = True
        print("[STOP] graceful stop requested")

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    appender = AtomicCSVAppender(output_path, HEADER)
    session = requests.Session()

    print("CANONICAL SOL MARKET COLLECTOR V1")
    print("URL_TEMPLATE =", args.url_template)
    print("SYMBOL =", SYMBOL)
    print("OUTPUT =", output_path)
    print("TARGET_INTERVAL_SEC =", args.interval_sec)
    print("MAX_STATE_GAP_SEC =", args.max_state_gap_sec)
    print("SERVER_TIMESTAMP_REQUIRED = false")
    print("STOP = Ctrl+C")

    next_request = time.monotonic()

    try:
        while not stop_requested[0]:
            sleep_for = next_request - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

            request_ms = now_epoch_ms()
            try:
                response = session.get(
                    args.url_template.format(symbol=SYMBOL),
                    timeout=args.timeout_sec,
                )
                received_ms = now_epoch_ms()
                response.raise_for_status()
                data = response.json()
                snapshot = extract_snapshot(data)

                server_ms, server_kind = parse_server_timestamp(data)
                snapshot["server_timestamp_available"] = server_ms is not None
                snapshot["server_timestamp_epoch_ms"] = server_ms

                record = build_record(
                    snapshot,
                    request_ms,
                    received_ms,
                    previous,
                    args.max_state_gap_sec,
                )
                record.extend([session_id, reconnect_count])
                appender.append(record)

                if had_failure:
                    reconnect_count += 1
                    print("[RECONNECT] request recovered; reconnect_count=%d" % reconnect_count)
                    had_failure = False

                previous = dict(snapshot)
                previous["received_ms"] = received_ms

                print(
                    "[OK]",
                    now_local_iso(received_ms),
                    "latency_ms=%d" % (received_ms - request_ms),
                    "bid=%.10f" % snapshot["bid"],
                    "ask=%.10f" % snapshot["ask"],
                    "spread_pct=%.6f" % snapshot["spread_pct"],
                    "OBI10=%.6f" % snapshot["obi10"],
                    "OFI=%.10f" % record[26],
                    "gap=%s" % (record[28] if record[28] is not None else "NA"),
                    "state_reset=%s" % record[30],
                )

                if args.once:
                    break

                next_request = max(
                    next_request + args.interval_sec,
                    time.monotonic(),
                )

            except Exception as exc:
                received_ms = now_epoch_ms()
                had_failure = True
                previous = None
                print(
                    "[ERROR]",
                    now_local_iso(received_ms),
                    "|",
                    type(exc).__name__,
                    "|",
                    str(exc),
                    "| reconnect_count=%d" % reconnect_count,
                )
                next_request = time.monotonic() + min(
                    max(args.interval_sec, 1.0),
                    10.0,
                )

    finally:
        session.close()
        print("[STOPPED] output =", output_path)


if __name__ == "__main__":
    main()

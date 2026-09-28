# -*- coding: utf-8 -*-
"""
Canonical SOL matches collector v1.

Transport is the verified Bitpin REST latest-matches snapshot endpoint.
No orders are sent. No WebSocket protocol is assumed without a verified
public endpoint.
"""

import argparse
import csv
import datetime
import io
import os
import signal
import time

import requests


DEFAULT_URL = "https://api.bitpin.org/api/v1/mth/matches/SOL_USDT/"
SYMBOL = "SOL_USDT"
DEFAULT_OUTPUT = "canonical_sol_matches_v1.csv"
DEFAULT_POLL_SEC = 5.0
DEFAULT_TIMEOUT_SEC = 10.0
DEFAULT_RETRY_MAX_SEC = 60.0

HEADER = [
    "id",
    "event_time_epoch_ms",
    "event_time_iso",
    "received_at_epoch_ms",
    "received_at_iso",
    "request_sent_at_epoch_ms",
    "request_sent_at_iso",
    "response_latency_ms",
    "price",
    "base_amount",
    "quote_amount",
    "side",
    "symbol",
    "transport",
    "session_id",
    "reconnect_count",
]


def now_epoch_ms():
    return int(time.time() * 1000.0)


def local_iso(epoch_ms):
    return datetime.datetime.fromtimestamp(
        epoch_ms / 1000.0
    ).astimezone().isoformat(timespec="milliseconds")


def finite(value):
    try:
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return None
        return x
    except (TypeError, ValueError):
        return None


def event_epoch_ms(value):
    x = finite(value)
    if x is None:
        return None
    if abs(x) > 100000000000:
        return int(x)
    if abs(x) > 1000000000:
        return int(x * 1000.0)
    return None


def repair_trailing_partial_line(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False

    with open(path, "rb+") as handle:
        handle.seek(-1, os.SEEK_END)
        if handle.read(1) in (b"\n", b"\r"):
            return False

        chunk_size = 4096
        size = handle.tell() + 1
        position = max(0, size - chunk_size)
        handle.seek(position)
        tail = handle.read(size - position)
        last_newline = max(tail.rfind(b"\n"), tail.rfind(b"\r"))
        if last_newline < 0:
            return False

        handle.truncate(position + last_newline + 1)
        handle.flush()
        os.fsync(handle.fileno())
        return True


def csv_line(values):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(values)
    return out.getvalue().encode("utf-8")


class AtomicCSVAppender(object):
    def __init__(self, path, header):
        self.path = path
        repaired = repair_trailing_partial_line(path)
        if repaired:
            print("[RECOVERY] removed incomplete trailing record:", path)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "ab") as handle:
                handle.write(csv_line(header))
                handle.flush()
                os.fsync(handle.fileno())

    def append(self, values):
        self.append_many([values])

    def append_many(self, rows):
        if not rows:
            return
        with open(self.path, "ab") as handle:
            for values in rows:
                handle.write(csv_line(values))
            handle.flush()
            os.fsync(handle.fileno())


def normalize_trade(item):
    trade_id = item.get("id")
    price = finite(item.get("price"))
    base_amount = finite(item.get("base_amount"))
    quote_amount = finite(item.get("quote_amount"))
    side = str(item.get("side") or "").strip().lower()
    event_ms = event_epoch_ms(item.get("time"))

    if not trade_id or price is None or price <= 0:
        return None
    if base_amount is None or base_amount < 0:
        return None
    if quote_amount is None or quote_amount < 0:
        return None
    if side not in ("buy", "sell"):
        return None

    return {
        "id": str(trade_id),
        "event_time_epoch_ms": event_ms,
        "event_time_iso": (
            datetime.datetime.fromtimestamp(
                event_ms / 1000.0, datetime.timezone.utc
            ).isoformat()
            if event_ms is not None
            else ""
        ),
        "price": price,
        "base_amount": base_amount,
        "quote_amount": quote_amount,
        "side": side,
    }


def append_unique_trades(appender, items, seen, request_ms, received_ms, session_id, reconnect_count):
    new_count = 0
    invalid_count = 0

    normalized = []
    for item in items:
        row = normalize_trade(item)
        if row is None:
            invalid_count += 1
            continue
        normalized.append(row)

    # Endpoint returns latest-first; append chronological order when possible.
    normalized.sort(
        key=lambda r: (
            r["event_time_epoch_ms"] is None,
            r["event_time_epoch_ms"] if r["event_time_epoch_ms"] is not None else 0,
            r["id"],
        )
    )

    rows_to_append = []
    for row in normalized:
        if row["id"] in seen:
            continue

        rows_to_append.append([
            row["id"],
            row["event_time_epoch_ms"] if row["event_time_epoch_ms"] is not None else "",
            row["event_time_iso"],
            received_ms,
            local_iso(received_ms),
            request_ms,
            local_iso(request_ms),
            received_ms - request_ms,
            row["price"],
            row["base_amount"],
            row["quote_amount"],
            row["side"],
            SYMBOL,
            "REST",
            session_id,
            reconnect_count,
        ])
        seen.add(row["id"])
        new_count += 1

    appender.append_many(rows_to_append)
    return new_count, invalid_count


def load_seen_ids(path):
    seen = set()
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return seen

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            trade_id = str(row.get("id") or "").strip()
            if trade_id:
                seen.add(trade_id)
    return seen


def parse_args():
    parser = argparse.ArgumentParser(
        description="Canonical SOL-only Bitpin matches collector v1."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--poll-sec", type=float, default=DEFAULT_POLL_SEC)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.poll_sec <= 0:
        raise SystemExit("poll-sec must be positive")

    output_path = os.path.abspath(args.output)
    session_id = "%d-%d" % (os.getpid(), now_epoch_ms())
    seen = load_seen_ids(output_path)
    appender = AtomicCSVAppender(output_path, HEADER)

    reconnect_count = 0
    had_failure = False
    stop_requested = [False]

    def request_stop(signum, frame):
        stop_requested[0] = True
        print("[STOP] graceful stop requested")

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    session = requests.Session()
    next_poll = time.monotonic()

    print("CANONICAL SOL MATCHES COLLECTOR V1")
    print("URL =", args.url)
    print("SYMBOL =", SYMBOL)
    print("OUTPUT =", output_path)
    print("TRANSPORT = REST polling")
    print("PING_PONG = NOT_APPLICABLE (not a WebSocket collector)")
    print("POLL_SEC =", args.poll_sec)
    print("STOP = Ctrl+C")
    print("EXISTING_UNIQUE_IDS =", len(seen))

    try:
        while not stop_requested[0]:
            delay = next_poll - time.monotonic()
            if delay > 0:
                time.sleep(delay)

            request_ms = now_epoch_ms()
            try:
                response = session.get(args.url, timeout=args.timeout_sec)
                received_ms = now_epoch_ms()
                response.raise_for_status()
                payload = response.json()

                if not isinstance(payload, list):
                    raise ValueError("matches endpoint did not return a list")

                if had_failure:
                    reconnect_count += 1
                    print("[RECONNECT] REST polling recovered")

                had_failure = False

                new_count, invalid_count = append_unique_trades(
                    appender,
                    payload,
                    seen,
                    request_ms,
                    received_ms,
                    session_id,
                    reconnect_count,
                )

                print(
                    "[OK]",
                    local_iso(received_ms),
                    "| API=%d | NEW=%d | INVALID=%d | TOTAL_UNIQUE=%d | LATENCY_MS=%d | RECONNECTS=%d"
                    % (
                        len(payload),
                        new_count,
                        invalid_count,
                        len(seen),
                        received_ms - request_ms,
                        reconnect_count,
                    )
                )

                if args.once:
                    break

                next_poll = max(next_poll + args.poll_sec, time.monotonic())

            except Exception as exc:
                received_ms = now_epoch_ms()
                had_failure = True
                print(
                    "[ERROR]",
                    local_iso(received_ms),
                    "|",
                    type(exc).__name__,
                    "|",
                    str(exc),
                )
                backoff = min(
                    DEFAULT_RETRY_MAX_SEC,
                    max(args.poll_sec, 1.0) * (2.0 ** min(reconnect_count, 6)),
                )
                print("[BACKOFF] seconds=%.1f" % backoff)
                time.sleep(backoff)
                next_poll = time.monotonic()

    finally:
        session.close()
        print("[STOPPED] output =", output_path)


if __name__ == "__main__":
    main()

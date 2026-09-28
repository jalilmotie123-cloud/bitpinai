# -*- coding: utf-8 -*-
import csv
import os
import tempfile
import unittest

from canonical_sol_market_collector_v1 import (
    AtomicCSVAppender,
    calculate_obi,
    calculate_ofi,
    build_record,
    classify_gap,
    parse_timestamp,
)
from canonical_sol_matches_collector_v1 import (
    HEADER as MATCH_HEADER,
    AtomicCSVAppender as MatchAppender,
    append_unique_trades,
)


class CanonicalSOLCollectionTests(unittest.TestCase):
    def test_obi(self):
        self.assertAlmostEqual(calculate_obi(3.0, 1.0), 0.5)
        self.assertEqual(calculate_obi(0.0, 0.0), 0.0)

    def test_ofi(self):
        value = calculate_ofi(
            100.0, 101.0, 2.0, 3.0,
            102.0, 103.0, 4.0, 5.0,
        )
        self.assertAlmostEqual(value, 3.0 - 4.0)

    def test_timestamp_parsing_epoch(self):
        sec, kind = parse_timestamp(1790000000)
        self.assertEqual(kind, "epoch_seconds_utc")
        self.assertEqual(sec, 1790000000)

        ms, kind = parse_timestamp(1790000000000)
        self.assertEqual(kind, "epoch_milliseconds_utc")
        self.assertEqual(ms, 1790000000.0)

    def test_timestamp_parsing_naive_is_local(self):
        value, kind = parse_timestamp("2026-09-28 12:00:00.000")
        self.assertEqual(kind, "naive_datetime_local")
        self.assertIsNotNone(value)

    def test_gap_detection(self):
        self.assertEqual(classify_gap(1.0), "normal")
        self.assertEqual(classify_gap(10.1), "warning")
        self.assertEqual(classify_gap(60.1), "outage")

    def test_reconnect_state_reset(self):
        previous = {
            "bid": 100.0,
            "ask": 101.0,
            "bid_vol1": 1.0,
            "ask_vol1": 1.0,
            "received_ms": 1000,
        }
        snapshot = {
            "bid": 101.0,
            "ask": 102.0,
            "mid": 101.5,
            "spread_pct": 0.99,
            "bid_vol1": 2.0,
            "ask_vol1": 1.0,
            "bid3": 2.0,
            "ask3": 1.0,
            "bid5": 2.0,
            "ask5": 1.0,
            "bid10": 2.0,
            "ask10": 1.0,
            "obi1": 0.33,
            "obi3": 0.33,
            "obi5": 0.33,
            "obi10": 0.33,
            "server_timestamp_available": False,
            "server_timestamp_epoch_ms": None,
        }
        record = build_record(
            snapshot,
            12000,
            13000,
            previous,
            10.0,
        )
        self.assertEqual(record[30], 1)
        self.assertEqual(record[25], 0.0)
        self.assertEqual(record[26], 0.0)

    def test_atomic_append(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "market.csv")
            appender = AtomicCSVAppender(path, ["a", "b"])
            appender.append([1, 2])
            with open(path, "rb") as handle:
                data = handle.read()
            self.assertTrue(data.endswith(b"\r\n"))
            self.assertIn(b"1,2\r\n", data)

    def test_matches_dedup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "matches.csv")
            appender = MatchAppender(path, MATCH_HEADER)
            seen = set()
            payload = [
                {"id": "2", "time": 1790000001, "price": 101, "base_amount": 1, "quote_amount": 101, "side": "buy"},
                {"id": "1", "time": 1790000000, "price": 100, "base_amount": 1, "quote_amount": 100, "side": "sell"},
                {"id": "2", "time": 1790000001, "price": 101, "base_amount": 1, "quote_amount": 101, "side": "buy"},
            ]
            new_count, invalid = append_unique_trades(
                appender, payload, seen, 1790000002000, 1790000002001, "test", 0
            )
            self.assertEqual(new_count, 2)
            self.assertEqual(invalid, 0)
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["id"] for r in rows}, {"1", "2"})


if __name__ == "__main__":
    unittest.main()

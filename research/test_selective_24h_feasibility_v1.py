# -*- coding: utf-8 -*-
import unittest

from selective_24h_feasibility_v1 import (
    FEE_SIDE,
    SCORE_THRESHOLD,
    SHORT_EXECUTION_PROVEN,
    determine_primary_status,
    evaluate_trade,
    score_record,
    select_nonoverlapping,
    summary,
)


class Selective24HTests(unittest.TestCase):
    def test_fixed_score_direction(self):
        scaling = {
            "obi10": {"mean": 0.0, "std": 1.0},
            "ofi_norm": {"mean": 0.0, "std": 1.0},
            "cvd_rate_60s": {"mean": 0.0, "std": 1.0},
        }
        record = {
            "obi10": 2.0,
            "ofi_norm": 1.5,
            "cvd_rate_60s": 1.0,
        }
        self.assertGreaterEqual(score_record(record, scaling), SCORE_THRESHOLD)

    def test_non_overlap_24h(self):
        base = {
            "entry_time": 1000.0,
            "signal_time": 1000.0,
            "side": "LONG",
        }
        rows = [
            dict(base),
            dict(base, entry_time=2000.0, signal_time=2000.0),
            dict(base, entry_time=90000.0, signal_time=90000.0),
        ]
        chosen = select_nonoverlapping(rows)
        self.assertEqual(len(chosen), 2)
        self.assertEqual(chosen[0]["entry_time"], 1000.0)
        self.assertEqual(chosen[1]["entry_time"], 90000.0)

    def test_long_cost_convention(self):
        market = [
            {"time": 0.0, "bid": 100.0, "ask": 101.0, "mid": 100.5},
            {"time": 86400.0, "bid": 110.0, "ask": 111.0, "mid": 110.5},
        ]
        result = evaluate_trade(market, 0, "LONG")
        expected = (
            110.0 * (1.0 - FEE_SIDE) /
            (101.0 * (1.0 + FEE_SIDE)) - 1.0
        )
        self.assertAlmostEqual(result["net_return"], expected, places=12)

    def test_summary_drawdown_and_profit_factor(self):
        stats = summary([0.10, -0.05, 0.02])
        self.assertEqual(stats["N"], 3)
        self.assertGreater(stats["profit_factor"], 1.0)
        self.assertGreaterEqual(stats["max_drawdown"], 0.0)

    def test_long_only_gate_ignores_unproven_short(self):
        self.assertFalse(SHORT_EXECUTION_PROVEN)
        primary = summary([0.010, 0.015, 0.012, 0.018, 0.011])
        status = determine_primary_status(
            primary_summary=primary,
            baseline_mean=0.005,
            cost_robust=True,
            positive_block_count=2,
            sufficient_sample=True,
            sufficient_coverage=True,
        )
        self.assertEqual(status, "GO-FOR-FURTHER-RESEARCH")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import unittest

from selective_24h_feasibility_v1 import (
    FEE_SIDE,
    SCORE_THRESHOLD,
    SHORT_EXECUTION_PROVEN,
    cost_robust_for_group,
    determine_primary_status,
    evaluate_trade,
    score_record,
    select_nonoverlapping,
    selection_timestamp,
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

    def test_nonoverlap_accepts_scored_records_with_entry_snapshot_time(self):
        rows = [
            {
                "entry_snapshot_time": 1000.0,
                "signal_time": 1000.0,
                "direction": "LONG",
            },
            {
                "entry_snapshot_time": 2000.0,
                "signal_time": 2000.0,
                "direction": "SHORT",
            },
            {
                "entry_snapshot_time": 90000.0,
                "signal_time": 90000.0,
                "direction": "LONG",
            },
        ]
        chosen = select_nonoverlapping(rows)
        self.assertEqual(len(chosen), 2)
        self.assertEqual(chosen[0]["entry_snapshot_time"], 1000.0)
        self.assertEqual(chosen[1]["entry_snapshot_time"], 90000.0)
        self.assertEqual(selection_timestamp(chosen[0]), 1000.0)

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

    def test_cost_robust_rejects_empty_mean_net(self):
        rows = [
            {"group": "selected_long_primary", "slippage_bps": 0, "mean_net": ""},
            {"group": "selected_long_primary", "slippage_bps": 5, "mean_net": 0.009},
            {"group": "selected_long_primary", "slippage_bps": 10, "mean_net": 0.008},
        ]
        self.assertFalse(cost_robust_for_group(rows, "selected_long_primary"))

    def test_cost_robust_rejects_missing_case(self):
        rows = [
            {"group": "selected_long_primary", "slippage_bps": 0, "mean_net": 0.010},
            {"group": "selected_long_primary", "slippage_bps": 5, "mean_net": 0.009},
        ]
        self.assertFalse(cost_robust_for_group(rows, "selected_long_primary"))

    def test_cost_robust_accepts_three_finite_positive_cases(self):
        rows = [
            {"group": "selected_long_primary", "slippage_bps": 0, "mean_net": 0.010},
            {"group": "selected_long_primary", "slippage_bps": 5, "mean_net": 0.009},
            {"group": "selected_long_primary", "slippage_bps": 10, "mean_net": 0.008},
        ]
        self.assertTrue(cost_robust_for_group(rows, "selected_long_primary"))

    def test_long_only_cost_robust_uses_primary_group_and_rejects_empty(self):
        primary_rows = [
            {"group": "selected_long_primary", "slippage_bps": 0, "mean_net": 0.010},
            {"group": "selected_long_primary", "slippage_bps": 5, "mean_net": 0.009},
            {"group": "selected_long_primary", "slippage_bps": 10, "mean_net": 0.008},
            {"group": "selected_long_plus_short", "slippage_bps": 0, "mean_net": -0.100},
            {"group": "selected_long_plus_short", "slippage_bps": 5, "mean_net": -0.100},
            {"group": "selected_long_plus_short", "slippage_bps": 10, "mean_net": -0.100},
        ]
        self.assertFalse(SHORT_EXECUTION_PROVEN)
        self.assertTrue(cost_robust_for_group(primary_rows, "selected_long_primary"))
        self.assertFalse(cost_robust_for_group([], "selected_long_primary"))
        self.assertFalse(cost_robust_for_group(
            [x for x in primary_rows if x["group"] == "selected_long_plus_short"],
            "selected_long_primary",
        ))

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

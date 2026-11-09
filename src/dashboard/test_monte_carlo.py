"""Offline Monte Carlo tests; no warehouse connection required."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from monte_carlo import CATEGORIES, simulate_revenue, summarize_revenue


def fixtures():
    future = pd.DataFrame({"category": CATEGORIES, "predicted_sales": [100.0] * 3})
    records = []
    for i, month in enumerate(pd.date_range("2014-01-01", periods=12, freq="MS"), 1):
        # Anti-correlated category shocks should cancel in monthly TOTAL.
        for category, error in zip(CATEGORIES, (float(i), -float(i), 5.0)):
            records.append({"category": category, "month": month, "role": "selected",
                            "actual": 100.0 + error, "predicted": 100.0})
            records.append({"category": category, "month": month, "role": "baseline",
                            "actual": 100.0 + error, "predicted": 90.0})
    return future, pd.DataFrame(records)


class MonteCarloChecks(unittest.TestCase):
    def test_joint_residual_vectors_preserve_cross_category_dependence(self):
        future, evaluated = fixtures()
        values = simulate_revenue(future, evaluated, draws=10000, seed=42)
        self.assertEqual(len(values), 10000)
        np.testing.assert_allclose(values, 305.0)

    def test_deterministic_category_scenarios_and_exclusion_of_baseline(self):
        future, evaluated = fixtures()
        a = simulate_revenue(future, evaluated, category="Furniture", draws=3000, seed=17)
        b = simulate_revenue(future, evaluated, category="Furniture", draws=3000, seed=17)
        np.testing.assert_array_equal(a, b)
        self.assertGreaterEqual(a.min(), 101)
        self.assertLessEqual(a.max(), 112)

    def test_floor_zero_applies_before_category_sum(self):
        future, evaluated = fixtures()
        future.loc[future.category == "Office Supplies", "predicted_sales"] = 1.0
        values = simulate_revenue(future, evaluated, draws=1000, seed=42)
        # Office Supplies: 1 - i is floored to 0 for i>=1.
        self.assertTrue(np.all(values >= 206.0))

    def test_summary_and_probability(self):
        result = summarize_revenue(np.array([0.0, 100.0, 200.0, 300.0]), target=200)
        self.assertEqual(result["downside_probability"], 50.0)
        self.assertEqual(result["p50"], 150.0)
        self.assertLess(result["p5"], result["p95"])

    def test_missing_month_or_duplicate_cannot_be_used(self):
        future, evaluated = fixtures()
        missing = evaluated.loc[~evaluated.month.eq(pd.Timestamp("2014-12-01"))]
        with self.assertRaises(ValueError):
            simulate_revenue(future, missing)
        duplicated = pd.concat([evaluated, evaluated.iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            simulate_revenue(future, duplicated)

    def test_invalid_configuration_is_rejected(self):
        future, evaluated = fixtures()
        with self.assertRaises(ValueError):
            simulate_revenue(future, evaluated, draws=10)
        with self.assertRaises(ValueError):
            simulate_revenue(future, evaluated, category="Other")
        with self.assertRaises(ValueError):
            summarize_revenue(np.array([100.0]), target=-1)


if __name__ == "__main__":
    unittest.main()

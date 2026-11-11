"""Standalone tests for the daily customer simulator; no database required."""
import unittest

import pandas as pd

from daily_customers import daily_purchasing_customers, daily_scenarios, daily_summary


class DailyCustomerSimulationTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2014-10-01")
        self.end = pd.Timestamp("2015-01-01")
        days = pd.date_range(self.start, self.end - pd.Timedelta(days=1), freq="D")
        # Multiple orders for a person on one date must not inflate the count.
        self.orders = pd.DataFrame({
            "order_date": [days[0], days[0], days[0], days[2], days[7], days[7]],
            "customer_id": ["A", "A", "B", "A", "C", "D"]
        })

    def test_unique_customers_per_day_and_zero_days(self):
        history = daily_purchasing_customers(self.orders, self.start, self.end)
        self.assertEqual(history.iloc[0], 2)
        self.assertEqual(history.iloc[1], 0)
        self.assertEqual(history.iloc[2], 1)
        self.assertEqual(history.iloc[7], 2)
        self.assertEqual(len(history), 92)

    def test_only_past_dates_and_weekday_sampling(self):
        history = daily_purchasing_customers(self.orders, self.start, self.end)
        scenarios = daily_scenarios(history, simulations=200, seed=4)
        self.assertEqual(list(scenarios.columns),
                         list(pd.date_range("2015-01-01", periods=7, freq="D")))
        self.assertTrue((scenarios.to_numpy() >= 0).all())
        future = scenarios.columns[0]
        historical_values = set(history.loc[history.index.weekday == future.weekday()].tolist())
        self.assertTrue(set(scenarios[future].tolist()).issubset(historical_values))

    def test_reproducible_seed_and_risk(self):
        history = daily_purchasing_customers(self.orders, self.start, self.end)
        a = daily_scenarios(history, simulations=250, seed=2026)
        b = daily_scenarios(history, simulations=250, seed=2026)
        pd.testing.assert_frame_equal(a, b)
        high = daily_summary(a, capacity=100)
        low = daily_summary(a, capacity=0)
        self.assertTrue(high.over_capacity_pct.eq(0).all())
        self.assertTrue((low.over_capacity_pct >= 0).all())
        self.assertTrue((low.over_capacity_pct <= 100).all())
        self.assertTrue((high.low <= high.expected).all())
        self.assertTrue((high.expected <= high.high).all())

    def test_reject_short_or_invalid_period(self):
        with self.assertRaises(ValueError):
            daily_purchasing_customers(self.orders, self.start, self.start + pd.Timedelta(days=20))
        history = daily_purchasing_customers(self.orders, self.start, self.end)
        with self.assertRaises(ValueError):
            daily_scenarios(history.iloc[1:])
        with self.assertRaises(ValueError):
            daily_summary(pd.DataFrame(), capacity=1)


if __name__ == "__main__":
    unittest.main()

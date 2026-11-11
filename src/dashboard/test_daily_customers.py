"""Standalone tests for the daily customer simulator; no database required."""
import unittest

import pandas as pd

from daily_customers import (daily_purchasing_customers, daily_scenarios,
                             daily_summary, seasonal_customer_scenarios, monthly_summary)


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
        self.assertTrue((high.low <= high.high).all())
        self.assertTrue((high.expected >= 0).all())

    def test_one_calendar_month_and_twelve_months(self):
        history = daily_purchasing_customers(self.orders, self.start, self.end)
        one = seasonal_customer_scenarios(history, months=1, simulations=300, seed=7)
        year = seasonal_customer_scenarios(history, months=12, simulations=300, seed=7)
        self.assertEqual(len(one.columns), 31)
        self.assertEqual(one.columns[0], pd.Timestamp("2015-01-01"))
        self.assertEqual(one.columns[-1], pd.Timestamp("2015-01-31"))
        self.assertEqual(len(year.columns), 365)
        self.assertEqual(year.columns[-1], pd.Timestamp("2015-12-31"))
        monthly = monthly_summary(year)
        self.assertEqual(len(monthly), 12)
        self.assertEqual(monthly.month.iloc[0], pd.Timestamp("2015-01-01"))
        self.assertAlmostEqual(monthly.expected.sum(), year.sum(axis=1).mean())
        pd.testing.assert_frame_equal(one, seasonal_customer_scenarios(
            history, months=1, simulations=300, seed=7))

    def test_seasonal_month_weekday_matching(self):
        dates = pd.date_range("2011-01-01", "2014-12-31", freq="D")
        history = pd.Series([v.month * 10 + v.weekday() for v in dates],
                            index=dates)
        scenario = seasonal_customer_scenarios(history, months=12,
                                               simulations=200, seed=20)
        for date in scenario.columns:
            self.assertEqual(set(scenario[date]), {date.month * 10 + date.weekday()})

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

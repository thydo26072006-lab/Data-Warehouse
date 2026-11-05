"""Small checks for time ordering, the benchmark and metric definitions."""
import unittest
import numpy as np
import pandas as pd
from forecast import backtest, forecast, metrics


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.series = pd.Series(np.arange(1, 49, dtype=float),
                                index=pd.date_range("2011-01-01", periods=48, freq="MS"))

    def test_benchmark_uses_same_month_last_year(self):
        rows = pd.DataFrame(backtest(self.series, "seasonal_naive", "2014-01", "2014-12", "test"))
        np.testing.assert_array_equal(rows.predicted, np.arange(25, 37))
        self.assertTrue((rows.train_end < rows.month).all())

    def test_future_change_cannot_affect_earlier_predictions(self):
        original = backtest(self.series, "holt_winters", "2013-01", "2013-02", "test")
        changed = self.series.copy()
        changed.loc["2013-03":] *= 100
        repeated = backtest(changed, "holt_winters", "2013-01", "2013-02", "test")
        np.testing.assert_allclose([r["predicted"] for r in original], [r["predicted"] for r in repeated])

    def test_known_error_metrics(self):
        result = metrics(pd.DataFrame({"actual": [100, 200], "predicted": [90, 220]}))
        self.assertEqual(result["mae"], 15)
        self.assertAlmostEqual(result["rmse"], np.sqrt(250))
        self.assertEqual(result["wape_pct"], 10)

    def test_perfect_forecasts_have_zero_error(self):
        result = metrics(pd.DataFrame({"actual": [100, 200], "predicted": [100, 200]}))
        self.assertTrue(all(value == 0 for value in result.values()))


if __name__ == "__main__":
    unittest.main()

"""Integration checks against the real warehouse and the Streamlit application."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import psycopg
from streamlit.testing.v1 import AppTest

from data import ROOT, QUERIES, current_monthly, metadata, monthly_growth, olap


class DashboardChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        first, last, markets, categories = metadata()
        cls.filters = (first, (pd.Timestamp(last).replace(day=1) + pd.offsets.MonthBegin(1)).date(),
                       tuple(markets), tuple(categories))

    def app(self):
        return AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=45).run()

    def assert_clean(self, app):
        self.assertEqual([e.message for e in app.exception], [])
        self.assertEqual([e.value for e in app.error], [])

    def test_all_twelve_queries_match_existing_olap_outputs(self):
        for name in QUERIES:
            with self.subTest(query=name):
                actual = olap(name, self.filters)
                expected = pd.read_csv(ROOT / "results/warehouse/olap" / (name + ".csv"))
                pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-8, atol=1e-6)

    def test_filtered_kpis_match_source_and_order_composite_key(self):
        source = pd.read_csv(ROOT / "data/processed/superstore_processed.csv", parse_dates=["order_date"])
        filters = (pd.Timestamp("2014-01-01").date(), pd.Timestamp("2015-01-01").date(), ("US",), ("Technology",))
        rows = source[(source.order_date.dt.year == 2014) & source.market.eq("US") & source.category.eq("Technology")]
        actual = olap("01_overview", filters).iloc[0]
        self.assertAlmostEqual(actual.sales, rows.sales.sum(), places=5)
        self.assertAlmostEqual(actual.profit, rows.profit.sum(), places=5)
        self.assertEqual(actual.order_groups, len(rows.drop_duplicates(["order_id", "order_date", "customer_id"])))
        monthly = monthly_growth(filters)
        self.assertEqual(len(monthly), 12)
        self.assertAlmostEqual(monthly.sales.sum(), actual.sales, places=5)
        self.assertTrue(pd.isna(monthly.mom_growth.iloc[0]))
        self.assertTrue(monthly.yoy_growth.isna().all())

    def test_all_pages_and_all_explorer_choices_render(self):
        app = self.app()
        self.assert_clean(app)
        self.assertEqual(app.metric[0].value, "12.642.905")
        self.assertEqual(app.metric[3].value, "25.754")
        for page in ["Sản phẩm & thị trường", "Khách hàng & đơn hàng", "Khám phá OLAP", "Dự báo doanh thu"]:
            app.sidebar.radio[0].set_value(page).run()
            self.assert_clean(app)
            if page == "Khám phá OLAP":
                for name in QUERIES:
                    app.selectbox[0].set_value(name).run()
                    self.assert_clean(app)
            if page == "Dự báo doanh thu":
                self.assertEqual(app.metric[0].value, "352.375,83")
                self.assertEqual(app.metric[1].value, "9,63%")
                for category, wape in [("Furniture", "11,13%"), ("Office Supplies", "9,15%"), ("Technology", "15,76%")]:
                    app.selectbox[0].set_value(category).run()
                    self.assert_clean(app)
                    self.assertEqual(app.metric[1].value, wape)

    def test_filter_widgets_and_empty_selection(self):
        app = self.app()
        app.sidebar.multiselect[0].set_value(["US"])
        app.sidebar.multiselect[1].set_value(["Technology"])
        app.sidebar.select_slider[0].set_value(("2014-01", "2014-12")).run()
        self.assert_clean(app)
        rows = olap("01_overview", (pd.Timestamp("2014-01-01").date(), pd.Timestamp("2015-01-01").date(), ("US",), ("Technology",))).iloc[0]
        self.assertEqual(app.metric[0].value, f"{rows.sales:,.0f}".replace(",", "."))
        app.sidebar.multiselect[0].set_value([]).run()
        self.assert_clean(app)
        self.assertTrue(app.info)
        self.assertEqual(len(app.metric), 0)

    def test_stale_forecast_is_hidden(self):
        app = self.app()
        changed = current_monthly().copy()
        changed.loc[0, "sales"] += 1
        with patch("data.current_monthly", return_value=changed):
            app.sidebar.radio[0].set_value("Dự báo doanh thu").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 0)
        self.assertIn("Dữ liệu kho đã thay đổi", app.error[0].value)

    def test_linux_newlines_do_not_hide_valid_forecast(self):
        app = self.app()
        csv = ROOT / "results/forecasting/monthly_sales.csv"
        content = csv.read_bytes().replace(b"\r\n", b"\n")
        original_read = Path.read_bytes
        with patch.object(Path, "read_bytes", lambda path: content if path == csv else original_read(path)):
            app.sidebar.radio[0].set_value("Dự báo doanh thu").run()
        self.assert_clean(app)
        self.assertEqual(app.metric[0].value, "352.375,83")

    def test_changed_forecast_file_is_still_rejected(self):
        app = self.app()
        csv = ROOT / "results/forecasting/monthly_sales.csv"
        altered = csv.read_bytes().replace(b"Furniture", b"Furniture_changed", 1)
        original_read = Path.read_bytes
        with patch.object(Path, "read_bytes", lambda path: altered if path == csv else original_read(path)):
            app.sidebar.radio[0].set_value("Dự báo doanh thu").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 0)
        self.assertIn("Dữ liệu kho đã thay đổi", app.error[0].value)

    def test_connection_failure_shows_recovery_message(self):
        with patch("data.metadata", side_effect=psycopg.OperationalError("test connection failure")):
            app = self.app()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("Không thể tải dữ liệu", app.error[0].value)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DashboardChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = ROOT / "results/dashboard"
    output.mkdir(parents=True, exist_ok=True)
    (output / "checks.json").write_text(json.dumps({
        "status": "passed" if result.wasSuccessful() else "failed",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "coverage": ["12 SQL outputs reconciled", "filtered KPI and composite order count",
                     "5 pages and 12 explorer choices", "3 forecast categories and total",
                     "UI filters and empty selection", "stale forecasts hidden", "connection failure handled",
                     "Linux CSV newlines accepted", "changed CSV content rejected"]}, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)

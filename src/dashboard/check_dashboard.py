"""Integration checks against the real warehouse and the Streamlit application."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import psycopg
from streamlit.testing.v1 import AppTest

from data import ROOT, QUERIES, current_monthly, metadata, monthly_growth, olap, product_details
from insights import customer_orders, customer_kpis, segment_breakdown, sales_lines, state_sales


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
                # CUBE text ordering depends on the PostgreSQL database collation.
                if name == "09_market_category_cube":
                    actual = actual.sort_values(["market", "category"], na_position="last").reset_index(drop=True)
                    expected = expected.sort_values(["market", "category"], na_position="last").reset_index(drop=True)
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

    def test_new_olap_views_and_product_drilldown(self):
        app = self.app()
        self.assert_clean(app)
        self.assertIn("ROLLUP doanh thu theo thời gian", [x.value for x in app.subheader])
        # Product-level query must not duplicate or lose rows under a composite product key.
        grouped = olap("04_product_drilldown", self.filters)
        expected = grouped[(grouped.category == "Furniture") &
                           (grouped.sub_category == "Tables")].iloc[0]
        details = product_details(self.filters, "Furniture", "Tables")
        self.assertAlmostEqual(details.sales.sum(), expected.sales, places=5)
        self.assertAlmostEqual(details.profit.sum(), expected.profit, places=5)
        app.sidebar.radio[0].set_value("Sản phẩm & thị trường").run()
        self.assert_clean(app)
        self.assertIn("Heatmap biên lợi nhuận: ngành hàng × thị trường",
                      [x.value for x in app.subheader])
        year_selector = next(x for x in app.selectbox if x.key == "heatmap_year")
        self.assertEqual(year_selector.value, "Toàn giai đoạn")
        self.assertEqual([str(value) for value in year_selector.options],
                         ["Toàn giai đoạn", "2011", "2012", "2013", "2014"])
        year_selector.set_value(2014).run()
        self.assert_clean(app)
        self.assertEqual(next(x for x in app.selectbox if x.key == "heatmap_year").value, 2014)
        app.selectbox[0].set_value("Furniture").run()
        app.selectbox[1].set_value("Tables").run()
        self.assert_clean(app)

    def test_bottom_ten_countries_match_sql_geography(self):
        # Country totals must aggregate all (market, region, country) rows before ranking.
        geography = olap("05_geography", self.filters)
        country_totals = geography.groupby("country", as_index=False)[["sales", "profit"]].sum()
        low_sales = country_totals.nsmallest(10, "sales")
        low_profit = country_totals.nsmallest(10, "profit")
        self.assertEqual(len(low_sales), 10)
        self.assertEqual(len(low_profit), 10)
        self.assertEqual(low_sales.iloc[0].country, "Equatorial Guinea")
        self.assertEqual(low_profit.iloc[0].country, "Turkey")
        app = self.app()
        app.sidebar.radio[0].set_value("Sản phẩm & thị trường").run()
        self.assert_clean(app)
        self.assertIn("10 quốc gia có doanh thu và lợi nhuận thấp nhất",
                      [item.value for item in app.subheader])

    def test_forecast_diagnostics_without_changing_published_metrics(self):
        app = self.app()
        app.sidebar.radio[0].set_value("Dự báo doanh thu").run()
        self.assert_clean(app)
        self.assertIn("Chẩn đoán sai số dự báo năm 2014",
                      [x.value for x in app.subheader])
        self.assertEqual(app.metric[0].value, "352.375,83")
        self.assertEqual(app.metric[1].value, "9,63%")
        self.assertGreaterEqual(len(app.metric), 6)

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

    def test_customer_behavior_and_segment_totals(self):
        orders = customer_orders(self.filters)
        k = customer_kpis(orders, self.filters[0], self.filters[1], 12)
        segments = segment_breakdown(orders, self.filters[0], self.filters[1])
        self.assertGreater(k["active"], 0)
        self.assertEqual(k["active"], k["new"] + k["returning"])
        self.assertAlmostEqual(k["returning_pct"], 100 * k["returning"] / k["active"], places=6)
        self.assertLessEqual(k["repeat"], k["active"])
        self.assertLessEqual(k["inactive"], k["previous"])
        self.assertEqual(int(segments.customers.sum()), k["active"])
        self.assertAlmostEqual(segments.share_pct.sum(), 100, places=6)
        self.assertEqual(set(segments.segment), {"Consumer", "Corporate", "Home Office"})
        app = self.app()
        app.sidebar.radio[0].set_value("Khách hàng & đơn hàng").run()
        self.assert_clean(app)
        self.assertIn("Phân khúc khách hàng và hành vi mua sắm",
                      [x.value for x in app.subheader])
        self.assertIn("Phân tích tương quan giữa các chỉ tiêu",
                      [x.value for x in app.subheader])
        self.assertIn("Tỷ lệ khách hàng quay lại", [m.label for m in app.metric])
        self.assertIn("Rủi ro lợi nhuận theo mức chiết khấu",
                      [x.value for x in app.subheader])

    def test_line_level_correlation_and_us_map_source(self):
        rows = sales_lines(self.filters)
        overview = olap("01_overview", self.filters).iloc[0]
        self.assertEqual(len(rows), overview.sales_lines)
        self.assertAlmostEqual(rows.sales.sum(), overview.sales, places=4)
        self.assertTrue(rows.discount.between(0, 1).all())
        states = state_sales(self.filters)
        us = olap("05_geography", self.filters)
        us = us.loc[us.country.eq("United States")]
        self.assertAlmostEqual(states.sales.sum(), us.sales.sum(), places=4)
        self.assertGreater(len(states), 0)
        app = self.app()
        app.sidebar.radio[0].set_value("Sản phẩm & thị trường").run()
        self.assert_clean(app)
        self.assertIn("Bản đồ doanh thu và biên lợi nhuận theo địa lý",
                      [x.value for x in app.subheader])
        self.assertIn("Boxplot doanh thu theo thị trường và ngành hàng",
                      [x.value for x in app.subheader])
        boxplot = next(x for x in app.radio if x.key == "sales_boxplot_mode")
        self.assertEqual(boxplot.value, "Theo thị trường")
        boxplot.set_value("Theo ngành hàng").run()
        self.assert_clean(app)

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

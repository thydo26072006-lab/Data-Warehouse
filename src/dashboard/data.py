"""Read-only, parameterized PostgreSQL queries for the dashboard."""
from pathlib import Path
from decimal import Decimal
import os
import re

import pandas as pd
import psycopg
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DSN = "postgresql://superstore@127.0.0.1:55432/superstore_dw?sslmode=disable"
text = (ROOT / "src/warehouse/sql/04_olap_queries.sql").read_text(encoding="utf-8")
QUERIES = {name: sql.strip().rstrip(";") for name, sql in
           re.findall(r"-- name: (\w+)\s*\n(.*?)(?=-- name:|\Z)", text, re.S)}


@st.cache_data(ttl=60, show_spinner=False)
def query(sql, params=()):
    options = {"connect_timeout": 8, "options": "-c default_transaction_read_only=on -c statement_timeout=20000"}
    if "PGPASSFILE" not in os.environ:
        options["passfile"] = str(ROOT / ".runtime/pgpass.conf")
    with psycopg.connect(os.environ.get("SUPERSTORE_DATABASE_URL", DEFAULT_DSN), **options) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            frame = pd.DataFrame(cur.fetchall(), columns=[col.name for col in cur.description])
    # PostgreSQL NUMERIC arrives as Decimal; charts need regular numeric columns.
    for column in frame.select_dtypes("object"):
        if len(frame) and frame[column].dropna().map(lambda x: isinstance(x, Decimal)).any():
            frame[column] = pd.to_numeric(frame[column])
    return frame


def metadata():
    bounds = query("SELECT MIN(order_date) AS first_date, MAX(order_date) AS last_date FROM dw.fact_sales").iloc[0]
    markets = query("SELECT DISTINCT market FROM dw.dim_geography ORDER BY market").market.tolist()
    categories = query("SELECT DISTINCT category FROM dw.dim_product ORDER BY category").category.tolist()
    return bounds.first_date, bounds.last_date, markets, categories


def filter_clause(start, end, markets, categories):
    return ("order_date >= %s AND order_date < %s AND market = ANY(%s) AND category = ANY(%s)",
            (start, end, list(markets), list(categories)))


def olap(name, filters):
    where, params = filter_clause(*filters)
    # The query names and SQL text come only from the repository, never user SQL.
    sql = QUERIES[name].replace("dw.v_sales_analysis", "filtered")
    prefix = f"WITH filtered AS (SELECT * FROM dw.v_sales_analysis WHERE {where})"
    if sql.startswith("WITH "):
        sql = ", " + sql[5:]
    else:
        sql = " " + sql
    # Escape literal percentage signs for psycopg's parameter binding.
    return query(prefix + sql.replace("%", "%%"), params)


def monthly_growth(filters):
    where, params = filter_clause(*filters)
    sql = f"""
    WITH amounts AS (
      SELECT date_trunc('month',order_date)::date AS month, SUM(sales) AS sales, SUM(profit) AS profit
      FROM dw.v_sales_analysis WHERE {where} GROUP BY 1
    ), calendar AS (
      SELECT generate_series(%s::date, %s::date - INTERVAL '1 month', INTERVAL '1 month')::date AS month
    ), monthly AS (
      SELECT c.month,COALESCE(a.sales,0) AS sales,COALESCE(a.profit,0) AS profit
      FROM calendar c LEFT JOIN amounts a USING(month)
    ), previous AS (
      SELECT *,lag(sales) OVER(ORDER BY month) AS previous_month_sales,
               lag(sales,12) OVER(ORDER BY month) AS previous_year_sales FROM monthly
    )
    SELECT *, (sales-previous_month_sales)/NULLIF(previous_month_sales,0) AS mom_growth,
              (sales-previous_year_sales)/NULLIF(previous_year_sales,0) AS yoy_growth
    FROM previous ORDER BY month
    """
    return query(sql, (*params, filters[0], filters[1]))


def current_monthly():
    return query((ROOT / "src/forecasting/monthly_sales.sql").read_text(encoding="utf-8"))

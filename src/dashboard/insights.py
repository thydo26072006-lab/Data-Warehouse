"""Additional warehouse-backed insights; no CSV shortcuts or writes to PostgreSQL."""
import pandas as pd
from data import query, filter_clause


def customer_orders(filters):
    """Order grain across available history before selected end, preserving segment."""
    end = filters[1]
    return query("""
        SELECT customer_id, segment, order_id, order_date::date AS order_date,
               SUM(sales) AS sales, SUM(profit) AS profit
        FROM dw.v_sales_analysis
        WHERE order_date < %s AND market = ANY(%s) AND category = ANY(%s)
        GROUP BY customer_id, segment, order_id, order_date
        ORDER BY order_date, customer_id, order_id
    """, (end, list(filters[2]), list(filters[3])))


def customer_kpis(orders, start, end, lookback_months=12):
    """New/returning = first observed order in filtered market/product scope.

    Repeat = 2+ separate orders through end. Inactive proxy = prior customer
    without an order during the preceding N months. No true churn label exists.
    """
    empty = {"active": 0, "new": 0, "returning": 0, "repeat": 0,
             "repeat_pct": 0.0, "returning_pct": 0.0, "previous": 0, "inactive": 0, "inactive_pct": 0.0}
    if orders.empty:
        return empty
    data = orders.copy()
    data["order_date"] = pd.to_datetime(data["order_date"])
    first = data.groupby("customer_id").order_date.min()
    end_ts = pd.Timestamp(end)
    start_ts = pd.Timestamp(start)
    active_orders = data.loc[data.order_date.ge(start_ts) & data.order_date.lt(end_ts)]
    active = set(active_orders.customer_id)
    new = {c for c in active if first[c] >= start_ts}
    order_count = data.groupby("customer_id").size()
    repeat = sum(order_count[c] >= 2 for c in active)
    lookback_start = end_ts - pd.DateOffset(months=lookback_months)
    previous = set(first.index[first < lookback_start])
    recent = set(data.loc[data.order_date.ge(lookback_start), "customer_id"])
    inactive = previous - recent
    n_active = len(active)
    return {"active": n_active, "new": len(new), "returning": n_active - len(new),
            "returning_pct": 100 * (n_active - len(new)) / n_active if n_active else 0.,
            "repeat": int(repeat), "repeat_pct": 100 * repeat / n_active if n_active else 0.,
            "previous": len(previous), "inactive": len(inactive),
            "inactive_pct": 100 * len(inactive) / len(previous) if previous else 0.}


def segment_breakdown(orders, start, end):
    """Unique active customers and in-period sales/profit by customer segment."""
    if orders.empty:
        return pd.DataFrame(columns=["segment", "customers", "sales", "profit", "share_pct"])
    data = orders.copy()
    data["order_date"] = pd.to_datetime(data.order_date)
    rows = data.loc[data.order_date.ge(pd.Timestamp(start)) & data.order_date.lt(pd.Timestamp(end))]
    if rows.empty:
        return pd.DataFrame(columns=["segment", "customers", "sales", "profit", "share_pct"])
    summary = rows.groupby("segment", as_index=False).agg(
        customers=("customer_id", "nunique"), sales=("sales", "sum"), profit=("profit", "sum"))
    summary["share_pct"] = 100 * summary.customers / summary.customers.sum()
    return summary.sort_values("customers", ascending=False)


def sales_lines(filters):
    """All filtered sales lines for exact line-level correlation coefficients."""
    where, params = filter_clause(*filters)
    return query(f"""
        SELECT row_id, sales, profit, discount, quantity, market, category, sub_category
        FROM dw.v_sales_analysis WHERE {where}
        ORDER BY row_id
    """, params)


def state_sales(filters):
    """USA geographic distribution, stored as state names in the warehouse."""
    where, params = filter_clause(*filters)
    return query(f"""
        SELECT state, SUM(sales) AS sales, SUM(profit) AS profit,
               COUNT(*) AS sales_lines
        FROM dw.v_sales_analysis
        WHERE {where} AND country = 'United States'
        GROUP BY state ORDER BY sales DESC
    """, params)

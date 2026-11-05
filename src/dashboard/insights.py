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
        SELECT row_id, sales, profit, discount, quantity, shipping_cost, country, market, category, sub_category
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


CORRELATION_FIELDS = {
    "sales": "Doanh thu",
    "profit": "Lợi nhuận",
    "quantity": "Số lượng",
    "discount_pct": "Chiết khấu (%)",
    "shipping_cost": "Phí vận chuyển",
    "profit_per_unit": "Lợi nhuận/đơn vị",
    "margin_pct": "Biên lợi nhuận (%)",
}


CORRELATION_SCOPES = {
    "Toàn bộ dữ liệu": "all",
    "Quốc gia sinh lời": "profitable",
    "Quốc gia không sinh lời": "non_profitable",
    "Chiết khấu dưới 10%": "discount_below_10",
    "Chiết khấu trên 10%": "discount_above_10",
}


def correlation_dataset(rows, profitable_countries_only=False, scope=None):
    """Return numeric features at sales-line grain and observed country count.

    For legacy callers, profitable_countries_only=True selects profitable countries.
    Country profitability is assessed on all currently filtered sales lines, then
    all rows from matching countries are included in the group. The discount
    scopes are strictly < 10% and > 10%; exact 10% belongs to neither.
    """
    frame = rows.copy()
    selected = scope or ("profitable" if profitable_countries_only else "all")
    if selected not in CORRELATION_SCOPES.values():
        raise ValueError("Unsupported correlation scope")
    if selected in ("profitable", "non_profitable") and not frame.empty:
        country_profit = frame.groupby("country", dropna=False)["profit"].sum()
        if selected == "profitable":
            selected_countries = country_profit[country_profit.gt(0)].index
        else:
            selected_countries = country_profit[country_profit.le(0)].index
        frame = frame.loc[frame.country.isin(selected_countries)].copy()
    elif selected == "discount_below_10":
        frame = frame.loc[frame.discount.lt(0.10)].copy()
    elif selected == "discount_above_10":
        frame = frame.loc[frame.discount.gt(0.10)].copy()

    if frame.empty:
        return pd.DataFrame(columns=list(CORRELATION_FIELDS)), 0

    frame["discount_pct"] = frame["discount"] * 100
    frame["profit_per_unit"] = frame["profit"] / frame["quantity"].where(frame.quantity.ne(0))
    frame["margin_pct"] = 100 * frame["profit"] / frame["sales"].where(frame.sales.ne(0))
    return (
        frame[list(CORRELATION_FIELDS)].replace([float("inf"), float("-inf")], float("nan")),
        frame.country.nunique(),
    )


def correlation_matrix(rows, profitable_countries_only=False, scope=None):
    """Return labeled Pearson matrix, observation count and country count."""
    numeric, countries = correlation_dataset(rows, profitable_countries_only, scope=scope)
    if len(numeric) < 2:
        return pd.DataFrame(), len(numeric), countries
    return numeric.corr(method="pearson", min_periods=2).rename(
        index=CORRELATION_FIELDS, columns=CORRELATION_FIELDS
    ), len(numeric), countries

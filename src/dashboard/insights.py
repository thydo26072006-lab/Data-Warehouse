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


def customer_window(start, end, months):
    """Return an N-month analysis window ending at the chosen sidebar end.

    The window never extends before the sidebar's selected start, while
    customer_orders supplies earlier history for correct new/returning labels.
    End date is exclusive and aligned to the first day of the following month.
    """
    if months not in (3, 6, 12):
        raise ValueError("Supported customer analysis periods: 3, 6, 12 months")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    return max(start_ts, end_ts - pd.DateOffset(months=months)).date(), end_ts.date()


def customer_kpis(orders, start, end, lookback_months=12):
    """Unique customers, evaluated within [start,end), with pre-period history.

    New = first recorded purchase in the window, returning = purchased before
    the window AND within it; inactive is a proxy among customers whose first
    purchase preceded the window and who did not purchase in the window.
    The dataset is left-censored at the beginning of 2011.
    """
    empty = {"active": 0, "new": 0, "returning": 0, "repeat": 0,
             "repeat_pct": 0.0, "returning_pct": 0.0,
             "previous": 0, "inactive": 0, "inactive_pct": 0.0}
    if orders.empty:
        return empty
    data = orders.copy()
    data["order_date"] = pd.to_datetime(data["order_date"])
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    data = data.loc[data.order_date.lt(end_ts)]
    if data.empty:
        return empty
    first = data.groupby("customer_id").order_date.min()
    period = data.loc[data.order_date.ge(start_ts)]
    active = set(period.customer_id)
    new = set(first.index[first.ge(start_ts)]) & active
    returning = active - new
    # A repeated purchase is two or more separate order IDs within the window.
    repeat = int((period.groupby("customer_id").size() >= 2).sum())
    previous = set(first.index[first.lt(start_ts)])
    inactive = previous - active
    n_active = len(active)
    return {
        "active": n_active, "new": len(new), "returning": len(returning),
        "returning_pct": 100 * len(returning) / n_active if n_active else 0.,
        "repeat": repeat, "repeat_pct": 100 * repeat / n_active if n_active else 0.,
        "previous": len(previous), "inactive": len(inactive),
        "inactive_pct": 100 * len(inactive) / len(previous) if previous else 0.,
    }

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


def select_correlation_rows(rows, scope="all"):
    """Return sales lines for the selected correlation cohort."""
    if scope not in CORRELATION_SCOPES.values():
        raise ValueError("Unsupported correlation scope")
    frame = rows.copy()
    if scope in ("profitable", "non_profitable") and not frame.empty:
        country_profit = frame.groupby("country", dropna=False)["profit"].sum()
        selected = (country_profit.gt(0) if scope == "profitable"
                    else country_profit.le(0))
        frame = frame.loc[frame.country.isin(country_profit[selected].index)].copy()
    elif scope == "discount_below_10":
        frame = frame.loc[frame.discount.lt(0.10)].copy()
    elif scope == "discount_above_10":
        frame = frame.loc[frame.discount.gt(0.10)].copy()
    return frame


def country_performance(rows, scope="all"):
    """Country rankings with sales/profit and diagnostic indicators.

    Grouping, loss counts and ratios are based on the exact lines displayed.
    In discount cohorts, profit is for the selected discount subset, NOT
    the country's whole-period profit.
    """
    frame = select_correlation_rows(rows, scope)
    columns = ["country", "sales", "profit", "shipping_cost", "sales_lines",
               "loss_lines", "avg_discount_pct", "margin_pct", "loss_rate_pct", "status"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame = frame.copy()
    frame["loss_flag"] = frame.profit.lt(0).astype(int)
    summary = frame.groupby("country", as_index=False).agg(
        sales=("sales", "sum"), profit=("profit", "sum"),
        shipping_cost=("shipping_cost", "sum"),
        sales_lines=("profit", "size"), loss_lines=("loss_flag", "sum"),
        avg_discount=("discount", "mean"))
    summary["avg_discount_pct"] = 100 * summary.avg_discount
    summary["margin_pct"] = (100 * summary.profit /
                              summary.sales.where(summary.sales.ne(0)))
    summary["loss_rate_pct"] = 100 * summary.loss_lines / summary.sales_lines
    summary["status"] = summary.profit.map(
        lambda v: "Sinh lời" if v > 0 else "Lỗ" if v < 0 else "Hòa vốn")
    return summary[columns].sort_values(["profit", "country"], ascending=[True, True]).reset_index(drop=True)


def correlation_dataset(rows, profitable_countries_only=False, scope=None):
    """Return numeric features at sales-line grain and observed country count.

    For legacy callers, profitable_countries_only=True selects profitable countries.
    Country profitability is assessed on all currently filtered sales lines, then
    all rows from matching countries are included in the group. The discount
    scopes are strictly < 10% and > 10%; exact 10% belongs to neither.
    """
    selected = scope or ("profitable" if profitable_countries_only else "all")
    frame = select_correlation_rows(rows, selected)
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

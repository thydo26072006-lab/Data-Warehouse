"""Daily unique purchasing customers and historical resampling scenarios.

Customer counts come from distinct customer_id per order_date, not footfall.
Monthly totals below are sums of daily customer counts: repeat visitors on
different dates count again. No prediction beyond observed data is used to
construct the historical pools.
"""
import random

import pandas as pd


def daily_purchasing_customers(orders, start, end):
    """Count distinct purchasing customers for every calendar day in [start, end)."""
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end <= start:
        raise ValueError("Invalid historical date range")
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    if len(days) < 28:
        raise ValueError("At least 28 consecutive days are required")
    if orders.empty:
        return pd.Series(0, index=days, dtype="int64", name="customers")
    if not {"order_date", "customer_id"}.issubset(orders.columns):
        raise ValueError("Customer orders need dates and customer IDs")
    historical = orders[["order_date", "customer_id"]].copy()
    historical["order_date"] = pd.to_datetime(historical["order_date"]).dt.normalize()
    historical = historical.loc[historical.order_date.ge(start) &
                                historical.order_date.lt(end)]
    historical = historical.dropna(subset=["customer_id"]).drop_duplicates(
        ["order_date", "customer_id"]
    )
    count = historical.groupby("order_date").size()
    return count.reindex(days, fill_value=0).astype("int64").rename("customers")


def _validated_history(daily):
    if not isinstance(daily, pd.Series) or len(daily) < 28:
        raise ValueError("At least 28 days of transaction history are needed")
    if not isinstance(daily.index, pd.DatetimeIndex) or daily.index.has_duplicates:
        raise ValueError("History must use unique calendar dates")
    values = pd.to_numeric(daily, errors="coerce")
    dates = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    if (not daily.index.equals(dates) or values.isna().any() or
            (values < 0).any() or (values % 1 != 0).any()):
        raise ValueError("Daily history must be complete nonnegative integer counts")
    return values.astype(int)


def daily_scenarios(daily, *, horizon=7, simulations=10_000, seed=2026):
    """Compatibility: resample same-weekday observations for the next N days."""
    values = _validated_history(daily)
    if not 1 <= horizon <= 366 or not 100 <= simulations <= 100_000:
        raise ValueError("Invalid simulation length or sample size")
    rng = random.Random(seed)
    weekday = {w: values.loc[values.index.weekday == w].tolist() for w in range(7)}
    future = pd.date_range(values.index.max() + pd.Timedelta(days=1),
                           periods=horizon, freq="D")
    return pd.DataFrame({day: rng.choices(weekday[day.weekday()], k=simulations)
                         for day in future})


def seasonal_customer_scenarios(daily, months=1, *, simulations=2000, seed=2026):
    """Sample month+weekday analogues, with weekday fallback for sparse history.

    Forecast begins on the day following the selected data cutoff (typically
    the first of the next calendar month); month mode covers the following
    full calendar month(s). Results are scenarios, not validated confidence
    intervals or extrapolated trends.
    """
    values = _validated_history(daily)
    if months not in (1, 12) or not 100 <= simulations <= 100_000:
        raise ValueError("Choose a 1- or 12-month horizon")
    first = values.index.max() + pd.Timedelta(days=1)
    if first.day != 1:
        raise ValueError("Forecast cutoff must be at the end of a calendar month")
    stop = first + pd.DateOffset(months=months)
    future = pd.date_range(first, stop - pd.Timedelta(days=1), freq="D")
    rng = random.Random(seed)
    by_weekday = {w: values.loc[values.index.weekday == w].tolist() for w in range(7)}
    by_season = {(m, w): values.loc[(values.index.month == m) &
                                   (values.index.weekday == w)].tolist()
                 for m in range(1, 13) for w in range(7)}
    if not all(by_weekday.values()):
        raise ValueError("Historical weekdays are incomplete")
    scenarios = {}
    for date in future:
        analogues = by_season[(date.month, date.weekday())]
        pool = analogues if len(analogues) >= 4 else by_weekday[date.weekday()]
        scenarios[date] = rng.choices(pool, k=simulations)
    return pd.DataFrame(scenarios)


def daily_summary(scenarios, capacity):
    """Per-day mean, 10–90% scenario band, and probability above daily capacity."""
    if (not isinstance(scenarios, pd.DataFrame) or scenarios.empty or
            capacity < 0):
        raise ValueError("Invalid capacity or scenarios")
    return pd.DataFrame([
        {"date": pd.Timestamp(date),
         "expected": float(values.mean()),
         "low": float(values.quantile(.10)),
         "high": float(values.quantile(.90)),
         "over_capacity_pct": float(100 * values.gt(capacity).mean())}
        for date, values in scenarios.items()
    ])


def monthly_summary(scenarios):
    """Monthly sums of daily customer-visits, keeping simulated path pairing.

    One customer buying on two dates counts twice in the monthly *sum of daily
    distinct customers*; this is NOT monthly unique customer count.
    """
    if not isinstance(scenarios, pd.DataFrame) or scenarios.empty:
        raise ValueError("No simulated days to summarize")
    months = pd.DatetimeIndex(scenarios.columns).to_period("M")
    totals = scenarios.T.groupby(months).sum().T
    return pd.DataFrame([
        {"month": pd.Timestamp(month.start_time),
         "expected": float(values.mean()), "low": float(values.quantile(.10)),
         "high": float(values.quantile(.90))}
        for month, values in totals.items()
    ])

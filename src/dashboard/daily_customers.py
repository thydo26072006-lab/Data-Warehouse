"""Daily *purchasing* customer scenarios from recorded Global Superstore orders.

A customer is counted once per calendar day regardless of order count.
Historical zero-sales days are included. Scenarios are bootstrapped within
weekday from the selected historical window; they do not measure store visits,
predict emerging trends, or provide independently calibrated intervals.
"""
from datetime import timedelta
import random

import pandas as pd


def daily_purchasing_customers(orders, start, end):
    """Count unique purchasing customer IDs per day on [start, end)."""
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end <= start:
        raise ValueError("Invalid historical date range")
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    if len(days) < 28:
        raise ValueError("At least 28 consecutive calendar days are required")
    if orders.empty:
        return pd.Series(0, index=days, dtype="int64", name="customers")
    required = {"order_date", "customer_id"}
    if not required.issubset(orders.columns):
        raise ValueError("Customer orders must contain order_date and customer_id")
    historical = orders[["order_date", "customer_id"]].copy()
    historical["order_date"] = pd.to_datetime(historical["order_date"]).dt.normalize()
    historical = historical.loc[
        historical["order_date"].ge(start) & historical["order_date"].lt(end)
    ].dropna(subset=["customer_id"]).drop_duplicates(["order_date", "customer_id"])
    daily = historical.groupby("order_date").size()
    return daily.reindex(days, fill_value=0).astype("int64").rename("customers")


def daily_scenarios(daily, *, horizon=7, simulations=10_000, seed=2026):
    """Bootstrap weekday-specific daily purchasing customer counts, no lookahead."""
    if not isinstance(daily, pd.Series) or len(daily) < 28:
        raise ValueError("At least four complete weeks of history are required")
    if not 1 <= horizon <= 31 or not 100 <= simulations <= 100_000:
        raise ValueError("Invalid simulation configuration")
    if not isinstance(daily.index, pd.DatetimeIndex) or daily.index.has_duplicates:
        raise ValueError("History must have unique calendar dates")
    values = pd.to_numeric(daily, errors="coerce")
    if (values.isna().any() or (values < 0).any()
            or (values % 1 != 0).any()
            or not daily.index.equals(pd.date_range(daily.index.min(), daily.index.max(), freq="D"))):
        raise ValueError("History must be complete, non-negative integer day counts")
    rng = random.Random(seed)
    pools = {w: values.loc[daily.index.weekday == w].astype(int).tolist()
             for w in range(7)}
    future = pd.date_range(daily.index.max() + pd.Timedelta(days=1),
                           periods=horizon, freq="D")
    scenarios = {}
    for day in future:
        candidates = pools[day.weekday()]
        if not candidates:
            raise ValueError("No historical examples for this weekday")
        scenarios[day] = rng.choices(candidates, k=simulations)
    return pd.DataFrame(scenarios)


def daily_summary(scenarios, capacity):
    """Readable per-day forecast and share of scenarios above daily capacity."""
    if capacity < 0 or not isinstance(scenarios, pd.DataFrame) or scenarios.empty:
        raise ValueError("Invalid capacity or scenarios")
    rows = []
    for day in scenarios.columns:
        counts = scenarios[day]
        rows.append({
            "date": pd.Timestamp(day),
            "expected": float(counts.mean()),
            "low": float(counts.quantile(0.10)),
            "high": float(counts.quantile(0.90)),
            "over_capacity_pct": float(100 * counts.gt(capacity).mean()),
        })
    return pd.DataFrame(rows)

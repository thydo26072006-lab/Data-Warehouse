"""Residual-bootstrap Monte Carlo for the published January 2015 forecast.

Uses the 12 held-out 2014 one-step errors for exploratory calibration.
This is not a separately validated prediction interval. Category errors
are sampled jointly by month to preserve cross-category dependence.
"""
import numpy as np
import pandas as pd

CATEGORIES = ("Furniture", "Office Supplies", "Technology")


def simulate_revenue(future: pd.DataFrame, evaluated: pd.DataFrame,
                     category: str | None = None, *, draws: int = 10_000,
                     seed: int = 2026) -> np.ndarray:
    """Simulate non-negative monthly revenue using joint monthly error vectors."""
    if not (100 <= draws <= 100_000):
        raise ValueError("Simulation count must be between 100 and 100000")
    if not (0 <= seed <= 2**32 - 1):
        raise ValueError("Seed must be a non-negative 32-bit integer")
    if category is not None and category not in CATEGORIES:
        raise ValueError("Unknown category")
    forecast = future.set_index("category")
    if len(forecast) != len(CATEGORIES) or set(forecast.index) != set(CATEGORIES):
        raise ValueError("Each category must have one next-month forecast")
    points = pd.to_numeric(forecast.loc[list(CATEGORIES), "predicted_sales"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(points).all() or (points < 0).any():
        raise ValueError("Forecasts must be finite and non-negative")
    samples = evaluated.loc[evaluated["role"].eq("selected"), ["category", "month", "actual", "predicted"]].copy()
    samples["month"] = pd.to_datetime(samples["month"])
    if samples.duplicated(["category", "month"]).any():
        raise ValueError("Duplicate category/month error")
    if not samples["category"].isin(CATEGORIES).all():
        raise ValueError("Unexpected backtest category")
    samples["error"] = pd.to_numeric(samples.actual, errors="coerce") - pd.to_numeric(samples.predicted, errors="coerce")
    matrix = samples.pivot(index="month", columns="category", values="error").reindex(columns=list(CATEGORIES)).sort_index()
    months = pd.date_range("2014-01-01", "2014-12-01", freq="MS")
    if (len(matrix) != 12 or not matrix.index.equals(months)
            or matrix.isna().any().any() or not np.isfinite(matrix.to_numpy(dtype=float)).all()):
        raise ValueError("Exactly 12 complete months of selected-model errors in 2014 are required")
    rng = np.random.default_rng(seed)
    errors = matrix.to_numpy(dtype=float)[rng.integers(0, 12, size=draws)]
    scenarios = np.maximum(points + errors, 0.0)
    if category is not None:
        return scenarios[:, CATEGORIES.index(category)]
    return scenarios.sum(axis=1)


def summarize_revenue(scenarios: np.ndarray, target: float) -> dict:
    """Return descriptive quantiles and simulated downside probability."""
    data = np.asarray(scenarios, dtype=float)
    if data.ndim != 1 or data.size == 0 or not np.isfinite(data).all() or (data < 0).any():
        raise ValueError("Scenarios must be a finite non-negative 1D array")
    if not np.isfinite(target) or target < 0:
        raise ValueError("Target must be finite and non-negative")
    p5, p50, p95 = np.percentile(data, [5, 50, 95])
    return {"p5": float(p5), "p50": float(p50), "p95": float(p95),
            "mean": float(data.mean()), "std": float(data.std(ddof=0)),
            "downside_probability": float(100 * np.mean(data < target))}

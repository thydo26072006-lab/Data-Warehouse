"""Monthly category revenue forecasts: validation in 2013, held-out test in 2014."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import statsmodels
from statsmodels.tsa.holtwinters import ExponentialSmoothing

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "warehouse"))
from warehouse import psql_command, query_csv

OUTPUT = ROOT / "results" / "forecasting"
MODELS = ("seasonal_naive", "holt_winters", "holt_winters_damped")
LABELS = {
    "seasonal_naive": "Cùng tháng năm trước",
    "holt_winters": "Holt–Winters",
    "holt_winters_damped": "Holt–Winters giảm xu hướng",
}


def forecast(history, model, steps=1):
    """Only history is accessible here; target months are never passed to the model."""
    if model == "seasonal_naive":
        values = np.resize(history.iloc[-12:].to_numpy(), steps)
        fitted = None
    else:
        # Scaling by the training mean improves numerical optimization.
        scale = history.mean()
        fitted = ExponentialSmoothing(
            history / scale, trend="add", seasonal="add", seasonal_periods=12,
            damped_trend=(model == "holt_winters_damped"),
            initialization_method="estimated", missing="raise",
        ).fit(optimized=True, method="L-BFGS-B", minimize_kwargs={"options": {"maxiter": 2000}})
        if not fitted.mle_retvals["success"]:
            raise RuntimeError(f"Optimization failed for {model}: {fitted.mle_retvals}")
        values = fitted.forecast(steps).to_numpy() * scale
    if not np.isfinite(values).all():
        raise ValueError("Non-finite forecast")
    # Revenue cannot be negative; apply the same rule to every candidate.
    return np.maximum(values, 0), fitted


def backtest(series, model, start, end, category):
    rows = []
    for month in series.loc[start:end].index:
        history = series.loc[series.index < month]
        prediction, _ = forecast(history, model)
        rows.append({"category": category, "month": month,
                     "train_end": history.index[-1], "train_months": len(history),
                     "model": model, "actual": series.loc[month],
                     "predicted": prediction[0]})
    return rows


def metrics(rows):
    error = rows["actual"].to_numpy() - rows["predicted"].to_numpy()
    return {"mae": float(np.abs(error).mean()),
            "rmse": float(np.sqrt(np.square(error).mean())),
            "wape_pct": float(100 * np.abs(error).sum() / rows["actual"].abs().sum())}


def save_csv(frame, filename):
    frame.to_csv(OUTPUT / filename, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")


def plot_results(monthly, test, future, scores):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 1, figsize=(13, 12), layout="constrained")
    for ax, category in zip(axes, sorted(monthly.category.unique())):
        history = monthly.loc[monthly.category == category]
        evaluated = test[(test.category == category) & (test.role == "selected")]
        next_month = future[future.category == category]
        score = scores[(scores.category == category) & (scores.role == "selected")].iloc[0]
        ax.plot(history.month, history.sales / 1000, color="#66565E", label="Thực tế", lw=1.8)
        ax.axvspan(pd.Timestamp("2014-01-01"), pd.Timestamp("2014-12-31"), color="#FCE4F0", alpha=.7)
        ax.plot(evaluated.month, evaluated.predicted / 1000, color="#D80073",
                label="Dự báo từng tháng kiểm tra (2014)", lw=1.8, marker=".")
        ax.scatter(next_month.month, next_month.predicted_sales / 1000, color="#A50040",
                   marker="*", s=160, label="Dự báo tháng 01/2015", zorder=5)
        ax.set_title(f"{category} | {LABELS[score.model]} | WAPE: {score.wape_pct:.2f}%", loc="left", weight="bold")
        ax.set_ylabel("Doanh thu (nghìn đơn vị gốc)")
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
        ax.grid(axis="y", alpha=.18)
    axes[0].legend(loc="upper left", fontsize=9)
    fig.suptitle("Dự báo doanh thu theo nhóm sản phẩm", fontsize=20, weight="bold")
    fig.savefig(OUTPUT / "forecast_overview.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("SUPERSTORE_DATABASE_URL",
                        "postgresql://superstore@127.0.0.1:55432/superstore_dw?sslmode=disable"))
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    command = psql_command(args.dsn)
    monthly_csv = query_csv(command, (Path(__file__).parent / "monthly_sales.sql").read_text(encoding="utf-8"))
    monthly = pd.read_csv(io.StringIO(monthly_csv), parse_dates=["month"])
    expected_months = pd.date_range("2011-01-01", "2014-12-01", freq="MS")
    if set(monthly.category) != {"Furniture", "Office Supplies", "Technology"}:
        raise ValueError("Unexpected categories; review the evaluation setup")
    for category, group in monthly.groupby("category"):
        if not pd.DatetimeIndex(group.month).equals(expected_months):
            raise ValueError(f"{category}: missing, duplicated or unexpected months; do not fill silently")
    if monthly.sales.isna().any() or not (monthly.sales > 0).all():
        raise ValueError("Monthly revenue must be positive and complete")
    source = pd.read_csv(ROOT / "data" / "processed" / "superstore_processed.csv",
                         usecols=["order_date", "category", "sales"], parse_dates=["order_date"])
    source["month"] = source.order_date.dt.to_period("M").dt.to_timestamp()
    expected = source.groupby(["category", "month"]).sales.sum().sort_index()
    actual = monthly.set_index(["category", "month"]).sales.sort_index()
    pd.testing.assert_series_equal(actual, expected, rtol=0, atol=1e-6)
    save_csv(monthly, "monthly_sales.csv")

    validation_rows, test_rows, selections, future_rows, metric_rows = [], [], [], [], []
    for category, group in monthly.groupby("category", sort=True):
        series = group.set_index("month").sales.asfreq("MS")
        category_scores = []
        for model in MODELS:
            rows = backtest(series, model, "2013-01-01", "2013-12-01", category)
            validation_rows.extend(rows)
            category_scores.append({"category": category, "model": model,
                                    **metrics(pd.DataFrame(rows))})
        # Freeze the family using only validation scores. Test results do not enter this decision.
        best = min(category_scores, key=lambda row: row["wape_pct"])
        selections.append({"category": category, "model": best["model"],
                           "validation_wape_pct": best["wape_pct"]})
        for role, model in [("baseline", "seasonal_naive"), ("selected", best["model"])]:
            rows = pd.DataFrame(backtest(series, model, "2014-01-01", "2014-12-01", category))
            rows["role"] = role
            test_rows.extend(rows.to_dict("records"))
            metric_rows.append({"category": category, "role": role, "model": model, **metrics(rows)})
        prediction, fitted = forecast(series, best["model"])
        if fitted is not None:
            # Saved model operates on revenue / training mean; metadata stores that scale.
            fitted.save(OUTPUT / f"model_{category.lower().replace(' ', '_')}.pkl")
        future_rows.append({"category": category, "month": series.index[-1] + pd.offsets.MonthBegin(1),
                            "model": best["model"], "train_end": series.index[-1],
                            "training_scale": series.mean(), "predicted_sales": prediction[0],
                            "same_month_last_year": series.iloc[-12],
                            "predicted_yoy_pct": 100 * (prediction[0] / series.iloc[-12] - 1)})
        print(f"{category}: selected {best['model']} (validation WAPE {best['wape_pct']:.2f}%)", flush=True)

    validation, test = pd.DataFrame(validation_rows), pd.DataFrame(test_rows)
    future = pd.DataFrame(future_rows)
    for role, rows in test.groupby("role"):
        metric_rows.append({"category": "ALL_CATEGORY_MONTHS", "role": role,
                            "model": "category_specific" if role == "selected" else "seasonal_naive",
                            **metrics(rows)})
    totals = test.groupby(["role", "month"], as_index=False)[["actual", "predicted"]].sum()
    for role, rows in totals.groupby("role"):
        metric_rows.append({"category": "TOTAL_MONTHLY", "role": role,
                            "model": "bottom_up" if role == "selected" else "seasonal_naive", **metrics(rows)})
    scores = pd.DataFrame(metric_rows)
    selection = pd.DataFrame(selections)
    validation_scores = validation.groupby(["category", "model"]).apply(
        lambda group: pd.Series(metrics(group)), include_groups=False).reset_index()
    save_csv(validation, "validation_predictions.csv")
    save_csv(validation_scores, "validation_metrics.csv")
    save_csv(selection, "selected_models.csv")
    save_csv(test, "test_predictions.csv")
    save_csv(scores, "test_metrics.csv")
    save_csv(totals, "test_total_monthly.csv")
    save_csv(future, "forecast_next_month.csv")
    next_total = pd.DataFrame([{"month": future.month.iloc[0],
                                "predicted_sales": future.predicted_sales.sum(), "method": "bottom_up"}])
    save_csv(next_total, "forecast_total.csv")
    # Check the evaluation protocol and stored results, not just model fitting.
    assert (validation.train_end < validation.month).all() and (test.train_end < test.month).all()
    assert len(validation) == 108 and len(test) == 72
    assert validation.month.dt.year.eq(2013).all() and test.month.dt.year.eq(2014).all()
    assert np.isfinite(test.predicted).all() and np.isfinite(future.predicted_sales).all()
    assert future.month.eq(pd.Timestamp("2015-01-01")).all()
    for category in selection.category:
        chosen = selection.loc[selection.category == category, "model"].iloc[0]
        ranked = validation_scores[validation_scores.category == category].sort_values("wape_pct")
        assert chosen == ranked.iloc[0].model
    manifest = {"status": "passed", "created_at": datetime.now(timezone.utc).isoformat(),
                "data_source": "PostgreSQL dw.v_sales_analysis; order_date, category, SUM(sales)",
                "monthly_data_sha256": hashlib.sha256((OUTPUT / "monthly_sales.csv").read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                "months_per_category": 48, "categories": 3, "source_reconciliation": "all 144 monthly totals match processed CSV",
                "initial_training": "2011-01 through 2012-12", "validation": "2013-01 through 2013-12",
                "test": "2014-01 through 2014-12", "horizon_months": 1,
                "protocol": "Expanding window; refit before each month; family selected only on 2013 WAPE",
                "candidates": list(MODELS), "selection": selections,
                "final_forecast_month": "2015-01-01", "prediction_intervals": "not estimated",
                "versions": {"python": sys.version.split()[0], "pandas": pd.__version__,
                             "numpy": np.__version__, "statsmodels": statsmodels.__version__, "matplotlib": matplotlib.__version__}}
    (OUTPUT / "evaluation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_results(monthly, test, future, scores)
    print("\nHeld-out 2014 metrics:\n" + scores.to_string(index=False))
    print("\nNext-month forecast (January 2015):\n" + future.to_string(index=False))
    print(f"\nSaved to {OUTPUT}")


if __name__ == "__main__":
    main()

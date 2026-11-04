"""Streamlit dashboard for the Superstore warehouse and evaluated forecasts."""
import hashlib
import json

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

from data import ROOT, QUERIES, current_monthly, metadata, monthly_growth, olap, product_details

st.set_page_config(page_title="Superstore · Phân tích & dự báo", layout="wide")
st.markdown("""<style>
.stApp {background:#fffafd;} [data-testid="stSidebar"] {background:#fcecf4;}
.block-container {padding-top:2rem; max-width:1500px;}
[data-testid="stMetric"] {background:white;border:1px solid #f1d4e2;border-radius:14px;padding:18px;}
h1,h2,h3 {color:#71304f;} [data-testid="stMetricValue"] {color:#a50040;}
</style>""", unsafe_allow_html=True)

PINK = "#d80073"
PAGES = ["Tổng quan", "Sản phẩm & thị trường", "Khách hàng & đơn hàng", "Khám phá OLAP", "Dự báo doanh thu"]
TITLES = dict(zip(QUERIES, [
    "01 · Tổng quan", "02 · Tăng trưởng theo tháng", "03 · ROLLUP thời gian",
    "04 · Drill-down sản phẩm", "05 · Địa lý", "06 · Phân khúc khách hàng",
    "07 · Top 20 khách hàng", "08 · Vận chuyển & ưu tiên đơn",
    "09 · CUBE thị trường × nhóm hàng", "10 · Slice & dice: Technology, US/EU, 2014",
    "11 · Sản phẩm có tổng lợi nhuận âm", "12 · Phân tích mức chiết khấu"]))
NAMES = {"sales": "Doanh thu", "profit": "Lợi nhuận", "quantity": "Số lượng bán",
         "profit_margin": "Biên lợi nhuận", "order_groups": "Số đơn hàng", "customers": "Khách hàng",
         "category": "Nhóm sản phẩm", "sub_category": "Phân nhóm", "market": "Thị trường",
         "country": "Quốc gia", "region": "Khu vực", "month": "Tháng", "segment": "Phân khúc",
         "customer_name": "Tên khách hàng", "ship_mode": "Cách vận chuyển", "order_priority": "Ưu tiên",
         "shipping_cost": "Chi phí vận chuyển", "discount_band": "Mức chiết khấu",
         "sales_lines": "Dòng bán hàng", "loss_lines": "Dòng lỗ", "predicted_sales": "Doanh thu dự báo",
         "same_month_last_year": "Cùng tháng năm trước", "predicted_yoy_pct": "Tăng trưởng dự báo (%)",
         "wape_pct": "WAPE (%)", "mae": "MAE", "rmse": "RMSE", "model": "Mô hình",
         "product_name": "Tên sản phẩm", "product_id": "Mã sản phẩm", "customer_id": "Mã khách hàng",
         "mom_growth": "Tăng trưởng tháng", "yoy_growth": "Tăng trưởng cùng kỳ",
         "calendar_year": "Năm", "calendar_quarter": "Quý", "calendar_month": "Tháng trong năm"}


def number(value, digits=0):
    if pd.isna(value):
        return "—"
    return f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def table(frame, filename, label="Xem bảng dữ liệu"):
    with st.expander(label):
        configs = {col: st.column_config.NumberColumn(format="percent")
                   for col in frame if col in {"profit_margin", "mom_growth", "yoy_growth"}}
        st.dataframe(frame.rename(columns=NAMES), width="stretch", hide_index=True,
                     column_config={NAMES.get(key, key): value for key, value in configs.items()})
        st.download_button("Tải CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                           filename + ".csv", "text/csv", key="download_" + filename)


def bar(frame, dimension, measure="sales", limit=15, ascending=False):
    data = frame.sort_values(measure, ascending=ascending).head(limit)
    chart = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X(f"{measure}:Q", title=NAMES.get(measure, measure)),
        y=alt.Y(f"{dimension}:N", sort="x" if ascending else "-x", title=None),
        color=alt.condition(alt.datum[measure] < 0, alt.value("#a50040"), alt.value(PINK)),
        tooltip=[alt.Tooltip(f"{dimension}:N", title=NAMES.get(dimension, dimension)),
                 alt.Tooltip(f"{measure}:Q", title=NAMES.get(measure, measure), format=",.2f")],
    ).properties(height=max(210, len(data) * 28))
    st.altair_chart(chart, width="stretch")


def lines(frame, columns, labels, height=330):
    data = frame.melt(id_vars="month", value_vars=columns, var_name="series", value_name="value")
    data["series"] = data.series.map(labels)
    chart = alt.Chart(data).mark_line(point=True).encode(
        x=alt.X("month:T", title="Tháng", axis=alt.Axis(format="%m/%Y")),
        y=alt.Y("value:Q", title="Doanh thu / lợi nhuận", scale=alt.Scale(zero=False)),
        color=alt.Color("series:N", title=None, scale=alt.Scale(range=[PINK, "#5e6472", "#d59ab8"])),
        tooltip=[alt.Tooltip("month:T", title="Tháng", format="%m/%Y"),
                 alt.Tooltip("series:N", title="Chỉ tiêu"), alt.Tooltip("value:Q", format=",.2f", title="Giá trị")],
    ).properties(height=height).interactive()
    st.altair_chart(chart, width="stretch")


def overview(filters, summary):
    cols = st.columns(4)
    for col, label, value in zip(cols, ["Doanh thu", "Lợi nhuận", "Biên lợi nhuận", "Số đơn hàng"],
                                  [number(summary.sales), number(summary.profit),
                                   number(summary.profit_margin * 100, 2) + "%" if pd.notna(summary.profit_margin) else "—",
                                   number(summary.order_groups)]):
        col.metric(label, value)
    st.subheader("Diễn biến kinh doanh")
    monthly = monthly_growth(filters)
    monthly["month"] = pd.to_datetime(monthly.month)
    lines(monthly, ["sales", "profit"], NAMES)
    st.caption("Đơn vị tiền tệ theo dữ liệu gốc. Số đơn được đếm theo tổ hợp mã đơn, ngày đặt và mã khách hàng.")
    latest = monthly.iloc[-1]
    left, right = st.columns(2)
    left.metric("Tăng trưởng doanh thu tháng cuối so tháng trước", "—" if pd.isna(latest.mom_growth) else number(latest.mom_growth * 100, 2) + "%")
    right.metric("Tăng trưởng tháng cuối so cùng kỳ", "—" if pd.isna(latest.yoy_growth) else number(latest.yoy_growth * 100, 2) + "%")
    st.caption("Tăng trưởng chỉ so với tháng có trong khoảng đã chọn; dấu — là thiếu kỳ so sánh hoặc doanh thu kỳ trước bằng 0.")
    table(monthly, "monthly_growth")
    st.subheader("ROLLUP doanh thu theo thời gian")
    period = st.radio("Mức tổng hợp", ["Năm", "Quý", "Tháng"], horizontal=True, key="rollup_period")
    rolled = olap("03_time_rollup", filters)
    level = {"Năm": 3, "Quý": 1, "Tháng": 0}[period]
    rolled = rolled.loc[rolled.grouping_level.eq(level)].copy()
    if not rolled.empty:
        rolled["period_label"] = rolled.calendar_year.astype(int).astype(str)
        if period != "Năm":
            rolled["period_label"] += "-Q" + rolled.calendar_quarter.astype(int).astype(str)
        if period == "Tháng":
            rolled["period_label"] = (rolled.calendar_year.astype(int).astype(str) + "-"
                                      + rolled.calendar_month.astype(int).astype(str).str.zfill(2))
        st.altair_chart(alt.Chart(rolled).mark_bar(color=PINK).encode(
            x=alt.X("period_label:N", sort=None, title=period),
            y=alt.Y("sales:Q", title="Doanh thu"),
            tooltip=["period_label:N", alt.Tooltip("sales:Q", format=",.2f"),
                     alt.Tooltip("profit:Q", format=",.2f")]
        ).properties(height=270), width="stretch")
    st.caption("Các mức tổng hợp lấy từ truy vấn SQL ROLLUP; không cộng dòng tổng với dòng chi tiết.")


def products(filters):
    measure = st.radio("Chỉ tiêu phân tích", ["sales", "profit"], format_func=NAMES.get, horizontal=True)
    left, right = st.columns(2)
    product = olap("04_product_drilldown", filters)
    with left:
        st.subheader("Theo phân nhóm sản phẩm")
        bar(product[product.sub_category.notna()], "sub_category", measure, limit=17)
    geo = olap("05_geography", filters)
    with right:
        st.subheader("Theo quốc gia · Top 15")
        countries = geo.groupby("country", as_index=False)[["sales", "profit"]].sum()
        bar(countries, "country", measure)
    st.subheader("Drill-down: ngành hàng → phân nhóm → sản phẩm")
    details = product.loc[product.sub_category.notna() & product.category.notna()].copy()
    categories = sorted(details.category.unique().tolist())
    chosen_category = st.selectbox("Chọn ngành hàng để đi sâu", categories, key="drill_category")
    subcategories = sorted(details.loc[details.category.eq(chosen_category), "sub_category"].unique().tolist())
    chosen_sub = st.selectbox("Chọn phân nhóm", subcategories, key="drill_subcategory")
    items = product_details(filters, chosen_category, chosen_sub)
    st.caption("Mỗi sản phẩm được xác định bằng cặp product_id + product_name; kết quả chịu tác động của bộ lọc OLAP.")
    if items.empty:
        st.info("Không tìm thấy sản phẩm trong phạm vi đã chọn.")
    else:
        bar(items, "product_name", measure, limit=10)
        table(items, "product_level_details", "Danh sách sản phẩm trong phân nhóm")
    st.subheader("Heatmap biên lợi nhuận: ngành hàng × thị trường")
    cube = olap("09_market_category_cube", filters)
    heat = cube.loc[cube.grouping_level.eq(0) & cube.sales.gt(0)].copy()
    if heat.empty:
        st.info("Không có dữ liệu để vẽ heatmap.")
    else:
        heat["margin_pct"] = heat.profit / heat.sales * 100
        heatmap = alt.Chart(heat).mark_rect().encode(
            x=alt.X("market:N", title="Thị trường"),
            y=alt.Y("category:N", title="Ngành hàng"),
            color=alt.Color("margin_pct:Q", title="Biên lợi nhuận (%)",
                            scale=alt.Scale(scheme="redblue", domainMid=0)),
            tooltip=["market:N", "category:N", alt.Tooltip("sales:Q", format=",.2f"),
                     alt.Tooltip("profit:Q", format=",.2f"),
                     alt.Tooltip("margin_pct:Q", format=".2f", title="Biên lợi nhuận (%)")]
        ).properties(height=235)
        st.altair_chart(heatmap, width="stretch")
        st.caption("Mỗi ô = SUM(profit) / SUM(sales) × 100%; chỉ dùng các dòng chi tiết CUBE (grouping_level = 0).")
    table(product, "product_drilldown")
    st.subheader("10 quốc gia có doanh thu và lợi nhuận thấp nhất")
    st.caption("Doanh thu thấp phản ánh quy mô bán hàng nhỏ, không đồng nghĩa với thua lỗ. "
               "Lợi nhuận thấp nhất được xếp theo giá trị tăng dần, bao gồm cả lợi nhuận âm.")
    bottom_sales = countries.nsmallest(10, "sales")
    bottom_profit = countries.nsmallest(10, "profit")
    left_low, right_low = st.columns(2)
    with left_low:
        st.markdown("**Bottom 10 · Doanh thu**")
        bar(bottom_sales, "country", "sales", limit=10, ascending=True)
    with right_low:
        st.markdown("**Bottom 10 · Lợi nhuận**")
        bar(bottom_profit, "country", "profit", limit=10, ascending=True)
    with st.expander("Bảng số liệu Bottom 10 quốc gia"):
        st.write("Doanh thu thấp nhất")
        st.dataframe(bottom_sales[["country", "sales", "profit"]].rename(columns=NAMES),
                     hide_index=True, width="stretch")
        st.write("Lợi nhuận thấp nhất")
        st.dataframe(bottom_profit[["country", "sales", "profit"]].rename(columns=NAMES),
                     hide_index=True, width="stretch")
    table(geo, "geography", "Chi tiết thị trường và địa lý")
    st.subheader("Sản phẩm cần theo dõi")
    losses = olap("11_loss_making_products", filters)
    st.caption("Các sản phẩm có tổng lợi nhuận âm trong phạm vi bộ lọc. Mã và tên sản phẩm cùng xác định một sản phẩm.")
    if losses.empty:
        st.info("Không có sản phẩm có tổng lợi nhuận âm trong phạm vi này.")
    else:
        st.dataframe(losses.head(20).rename(columns=NAMES), hide_index=True, width="stretch")
        table(losses, "loss_making_products", "Xem và tải toàn bộ sản phẩm lỗ")


def customers(filters):
    left, right = st.columns(2)
    segments = olap("06_customer_segments", filters)
    with left:
        st.subheader("Doanh thu theo phân khúc")
        bar(segments, "segment")
    with right:
        st.subheader("Lợi nhuận theo phân khúc")
        bar(segments, "segment", "profit")
    table(segments, "customer_segments")
    top = olap("07_top_customers", filters)
    table(top, "top_customers", "Top 20 khách hàng theo lợi nhuận")
    st.subheader("Đơn hàng & chiết khấu")
    shipping = olap("08_order_shipping", filters)
    discount = olap("12_discount_analysis", filters)
    left, right = st.columns(2)
    with left:
        bar(shipping.groupby("ship_mode", as_index=False)[["sales", "profit", "shipping_cost"]].sum(), "ship_mode", "shipping_cost")
    with right:
        bar(discount, "discount_band", "profit")
    table(shipping, "order_shipping", "Chi tiết vận chuyển và ưu tiên đơn")
    table(discount, "discount_analysis", "Chi tiết các mức chiết khấu")
    st.caption("Mối liên hệ giữa chiết khấu và lợi nhuận là quan sát lịch sử, chưa chứng minh tác động nhân quả.")


def explorer(filters):
    name = st.selectbox("Chọn phép phân tích", list(QUERIES), format_func=TITLES.get)
    result = monthly_growth(filters) if name == "02_monthly_growth" else olap(name, filters)
    if name in {"03_time_rollup", "04_product_drilldown", "09_market_category_cube"}:
        st.info("Bảng có các dòng tổng hợp. Không cộng các dòng chi tiết với dòng tổng vì sẽ đếm trùng.")
    if name == "10_slice_dice":
        st.caption("Truy vấn này cố định năm 2014, US/EU và Technology; bộ lọc bên trái được áp dụng thêm theo phép giao.")
    st.dataframe(result.rename(columns=NAMES), width="stretch", hide_index=True)
    st.download_button("Tải kết quả CSV", result.to_csv(index=False).encode("utf-8-sig"), name + ".csv", "text/csv")
    with st.expander("Giải thích phép tổng hợp"):
        st.write("ROLLUP thời gian: grouping_level 0 = tháng, 1 = quý, 3 = năm, 7 = toàn bộ. "
                 "CUBE: 0 = thị trường × nhóm hàng, 1 = theo thị trường, 2 = theo nhóm hàng, 3 = toàn bộ. "
                 "Giá trị trống ở các cột chiều của dòng tổng hợp mang nghĩa tất cả.")


def forecasts():
    folder = ROOT / "results/forecasting"
    try:
        manifest = json.loads((folder / "evaluation.json").read_text(encoding="utf-8"))
        history = pd.read_csv(folder / "monthly_sales.csv", parse_dates=["month"])
        test = pd.read_csv(folder / "test_predictions.csv", parse_dates=["month"])
        future = pd.read_csv(folder / "forecast_next_month.csv", parse_dates=["month"])
        scores = pd.read_csv(folder / "test_metrics.csv")
    except (OSError, ValueError):
        st.error("Chưa có bộ kết quả dự báo hợp lệ. Hãy chạy src/forecasting/forecast.py trước.")
        return
    live = current_monthly()
    live["month"] = pd.to_datetime(live.month)
    try:
        pd.testing.assert_frame_equal(history.sort_values(["category", "month"]).reset_index(drop=True),
                                      live.sort_values(["category", "month"]).reset_index(drop=True),
                                      check_dtype=False, atol=1e-6, rtol=0)
        # Git may convert Windows CRLF to LF during deployment. Compare the same
        # content in either newline convention, including manifests created before this fix.
        content = (folder / "monthly_sales.csv").read_bytes().replace(b"\r\n", b"\n")
        valid_hashes = {hashlib.sha256(content).hexdigest(),
                        hashlib.sha256(content.replace(b"\n", b"\r\n")).hexdigest()}
        assert manifest["monthly_data_sha256"] in valid_hashes
    except (AssertionError, KeyError):
        st.error("Dữ liệu kho đã thay đổi so với bộ dự báo. Chạy lại src/forecasting/forecast.py để cập nhật trước khi xem kết quả.")
        return
    st.caption("Dự báo doanh thu toàn bộ thị trường theo nhóm sản phẩm. Bộ lọc OLAP không áp dụng cho trang này.")
    selected = st.selectbox("Phạm vi dự báo", ["Tất cả nhóm sản phẩm", *sorted(future.category.unique())])
    total = selected == "Tất cả nhóm sản phẩm"
    view = future if total else future[future.category == selected]
    score_key = "TOTAL_MONTHLY" if total else selected
    compared = scores[scores.category == score_key]
    chosen = compared[compared.role == "selected"].iloc[0]
    baseline = compared[compared.role == "baseline"].iloc[0]
    c1, c2, c3 = st.columns(3)
    month_label = future.month.iloc[0].strftime("%m/%Y")
    c1.metric("Doanh thu dự báo · " + month_label, number(view.predicted_sales.sum(), 2))
    c2.metric("WAPE kiểm tra 2014 · mô hình chọn", number(chosen.wape_pct, 2) + "%")
    c3.metric("WAPE kiểm tra 2014 · đối chứng", number(baseline.wape_pct, 2) + "%")
    st.subheader("Thực tế và dự báo")
    historic = history if total else history[history.category == selected]
    evaluated = test if total else test[test.category == selected]
    actual = historic.groupby("month", as_index=False).sales.sum()
    predictions = evaluated.pivot_table(index="month", columns="role", values="predicted", aggfunc="sum").reset_index()
    chart_data = actual.merge(predictions, on="month", how="outer")
    chart_data = pd.concat([chart_data, pd.DataFrame({"month": [future.month.iloc[0]],
                                                   "next_forecast": [view.predicted_sales.sum()]})], ignore_index=True)
    # A separate mark keeps the out-of-sample January point visually distinct.
    long = chart_data.melt("month", value_vars=["sales", "selected", "baseline"], var_name="series", value_name="value").dropna()
    long["series"] = long.series.map({"sales": "Thực tế", "selected": "Dự báo kiểm tra 2014", "baseline": "Cùng tháng năm trước"})
    line = alt.Chart(long).mark_line().encode(
        x=alt.X("month:T", title="Tháng", axis=alt.Axis(format="%m/%Y")),
        y=alt.Y("value:Q", title="Doanh thu (đơn vị gốc)", scale=alt.Scale(zero=False)),
        color=alt.Color("series:N", title=None, scale=alt.Scale(range=["#c9a3b6", PINK, "#5e6472"])),
        tooltip=[alt.Tooltip("month:T", format="%m/%Y"), "series:N", alt.Tooltip("value:Q", format=",.2f")])
    point = alt.Chart(chart_data.dropna(subset=["next_forecast"])).mark_point(color=PINK, filled=True, size=170, shape="diamond", clip=False).encode(
        x="month:T", y="next_forecast:Q", tooltip=[alt.Tooltip("month:T", format="%m/%Y"), alt.Tooltip("next_forecast:Q", title="Dự báo mới", format=",.2f")])
    st.altair_chart((line + point).properties(height=380).interactive(), width="stretch")
    st.caption("Dấu hình thoi là dự báo tháng 01/2015, chưa có số thực tế. Các dự báo năm 2014 được thực hiện cuốn chiếu, trước một tháng.")
    table(view[["category", "month", "model", "predicted_sales", "same_month_last_year", "predicted_yoy_pct"]], "next_month_forecast", "Chi tiết dự báo tháng tiếp theo")
    table(compared[["role", "model", "mae", "rmse", "wape_pct"]], "forecast_evaluation", "Đánh giá mô hình và đối chứng")
    st.subheader("Chẩn đoán sai số dự báo năm 2014")
    # Use one actual observation per month and the selected one-step-ahead forecast.
    selected_rows = evaluated.loc[evaluated.role.eq("selected")]
    diagnostic = selected_rows.groupby("month", as_index=False)[["actual", "predicted"]].sum()
    full_history = historic.groupby("month", as_index=False).sales.sum().sort_values("month")
    full_history["previous_actual"] = full_history.sales.shift(1)
    diagnostic = diagnostic.merge(full_history[["month", "previous_actual"]], on="month", how="left")
    diagnostic["error"] = diagnostic.actual - diagnostic.predicted
    diagnostic["abs_error"] = diagnostic.error.abs()
    diagnostic["down_month"] = diagnostic.actual.lt(diagnostic.previous_actual)
    down = diagnostic.loc[diagnostic.down_month]
    valid_direction = diagnostic.loc[diagnostic.previous_actual.notna()]
    correct = ((valid_direction.actual - valid_direction.previous_actual) *
               (valid_direction.predicted - valid_direction.previous_actual) > 0).sum()
    wape_down = 100 * down.abs_error.sum() / down.actual.abs().sum() if not down.empty and down.actual.abs().sum() else float("nan")
    a, b, c = st.columns(3)
    a.metric("WAPE tháng doanh thu giảm", number(wape_down, 2) + "%" if pd.notna(wape_down) else "—")
    b.metric("Tháng giảm trong tập kiểm tra", str(len(down)) + "/12")
    c.metric("Dự báo đúng chiều thay đổi", f"{correct}/{len(valid_direction)}" if len(valid_direction) else "—")
    st.altair_chart(alt.Chart(diagnostic).mark_bar().encode(
        x=alt.X("month:T", title="Tháng kiểm tra", axis=alt.Axis(format="%m/%Y")),
        y=alt.Y("error:Q", title="Sai số thực tế − dự báo"),
        color=alt.condition("datum.down_month", alt.value("#a50040"), alt.value("#8d9aa8")),
        tooltip=[alt.Tooltip("month:T", format="%m/%Y"), alt.Tooltip("actual:Q", format=",.2f"),
                 alt.Tooltip("predicted:Q", format=",.2f"), alt.Tooltip("error:Q", format=",.2f"),
                 alt.Tooltip("down_month:N", title="Doanh thu giảm")]
    ).properties(height=270), width="stretch")
    st.caption("Màu đậm đánh dấu tháng doanh thu thực tế giảm so với tháng liền trước. "
               "Sai số âm nghĩa là mô hình dự báo cao hơn thực tế. Các tháng giảm được xác định sau khi có kết quả thực tế, chỉ để đánh giá mô hình.")
    largest = diagnostic.nlargest(5, "abs_error").copy()
    largest["month"] = largest.month.dt.strftime("%m/%Y")
    st.dataframe(largest[["month", "actual", "predicted", "error", "abs_error", "down_month"]]
                 .rename(columns={"month": "Tháng", "actual": "Thực tế", "predicted": "Dự báo",
                                  "error": "Sai số", "abs_error": "Sai số tuyệt đối",
                                  "down_month": "Tháng giảm"}), hide_index=True, width="stretch")
    st.caption("WAPE tháng giảm là chỉ số chẩn đoán bổ sung, không thay thế WAPE kiểm tra toàn kỳ.")
    with st.expander("Mô hình được xây dựng và đánh giá thế nào?"):
        st.write("Huấn luyện ban đầu: 2011–2012. Chọn mô hình trên 2013, kiểm tra trên 2014. "
                 "Mỗi mốc chỉ dùng dữ liệu trước tháng cần dự báo. Sau đánh giá, huấn luyện lại đến 12/2014 để dự báo 01/2015.")
        st.write("Mô hình đã chọn theo ngành hàng: " + "; ".join(
            str(row.category) + ": " + str(row.model) for row in future.itertuples(index=False)) + ".")
        st.caption("Tên mô hình được đọc từ kết quả thực nghiệm, không cố định trong giao diện.")
        st.write("WAPE càng thấp càng tốt; không phải độ chính xác phân loại. Chỉ có bốn năm lịch sử, "
                 "chưa ước lượng khoảng dự báo. Dự báo doanh thu hỗ trợ lập mục tiêu, chưa xác định được lượng nhập hàng.")
        st.caption("Thời điểm tạo kết quả: " + manifest["created_at"])


def main():
    with st.sidebar:
        st.markdown("## KHO DỮ LIỆU BÁN LẺ VÀ HỆ HỖ TRỢ QUYẾT ĐỊNH LẬP KẾ HOẠCH BÁN HÀNG")
        st.caption("Phân tích kinh doanh & hỗ trợ quyết định")
        page = st.radio("Điều hướng", PAGES, label_visibility="collapsed")
        if st.button("Làm mới dữ liệu", width="stretch"):
            st.cache_data.clear()
        st.divider()
    st.title(page)
    st.caption("GLOBAL SUPERSTORE  ·  KHO DỮ LIỆU & DỰ BÁO DOANH THU")
    try:
        if page == "Dự báo doanh thu":
            forecasts()
            return
        first, last, markets, categories = metadata()
        months = pd.date_range(pd.Timestamp(first).replace(day=1), pd.Timestamp(last).replace(day=1), freq="MS")
        options = [date.strftime("%Y-%m") for date in months]
        with st.sidebar:
            st.markdown("### Phạm vi phân tích")
            start, end = st.select_slider("Khoảng tháng", options=options, value=(options[0], options[-1]))
            chosen_markets = st.multiselect("Thị trường", markets, default=markets)
            chosen_categories = st.multiselect("Nhóm sản phẩm", categories, default=categories)
            st.caption("Bộ lọc áp dụng cho toàn bộ chỉ số và bảng OLAP trên trang.")
        filters = (pd.Timestamp(start + "-01").date(), (pd.Timestamp(end + "-01") + pd.offsets.MonthBegin(1)).date(),
                   tuple(chosen_markets), tuple(chosen_categories))
        if not chosen_markets or not chosen_categories:
            st.info("Chọn ít nhất một thị trường và một nhóm sản phẩm để xem dữ liệu.")
            return
        st.caption(f"{start} → {end}  ·  {len(chosen_markets)} thị trường  ·  {len(chosen_categories)} nhóm sản phẩm")
        summary = olap("01_overview", filters).iloc[0]
        if summary.sales_lines == 0:
            st.info("Không có giao dịch trong phạm vi đã chọn. Hãy thay đổi bộ lọc.")
            return
        if page == "Tổng quan":
            overview(filters, summary)
        elif page == "Sản phẩm & thị trường":
            products(filters)
        elif page == "Khách hàng & đơn hàng":
            customers(filters)
        else:
            explorer(filters)
    except psycopg.Error:
        st.error("Không thể tải dữ liệu. Kiểm tra PostgreSQL đã chạy và kho đã được nạp; sau đó nhấn Làm mới dữ liệu.")
        st.caption("Khởi động kho: python src/warehouse/setup_local_postgres.py. Cấu hình kết nối qua SUPERSTORE_DATABASE_URL nếu dùng máy chủ khác.")


if __name__ == "__main__":
    main()

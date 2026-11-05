"""Streamlit dashboard for the Superstore warehouse and evaluated forecasts."""
import hashlib
import json

import altair as alt
import pandas as pd
import psycopg
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from insights import customer_orders, customer_kpis, customer_window, segment_breakdown, sales_lines, state_sales, correlation_matrix, CORRELATION_SCOPES
from chatbot import EXAMPLES as CHAT_EXAMPLES, answer_question

from data import ROOT, QUERIES, current_monthly, metadata, monthly_growth, olap, product_details

st.set_page_config(page_title="Superstore · Phân tích & dự báo", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800&display=swap');
html, body, .stApp, [data-testid="stSidebar"], .stMarkdown,
[data-testid="stMetric"], [data-testid="stWidgetLabel"],
[data-testid="stTable"], [data-testid="stDataFrame"] {
 font-family: 'Nunito', 'Segoe UI', sans-serif !important;
}
h1, h2, h3, h4, p, label, button {font-family:'Nunito','Segoe UI',sans-serif !important;}
:root {--navy:#172f50; --orange:#ca7045; --cream:#fffdf9; --sky:#e8f4f8;}
.stApp {background:#fffdf9; color:#273447;}
[data-testid="stSidebar"] {background:#e9f3f7; border-right:1px solid #d8e3eb;}
.block-container {padding-top:1.35rem; max-width:1560px; padding-bottom:2rem;}
[data-testid="stMetric"] {background:#ffffff;border:1px solid #dae4eb;border-radius:12px;
 padding:17px 15px;box-shadow:0 2px 9px rgba(26,48,78,.055);min-width:0;}
[data-testid="stMetricLabel"] {color:#956145;font-size:.89rem;font-weight:650;}
[data-testid="stMetricValue"] {color:#183451;font-size:clamp(1.1rem,2.0vw,1.8rem);letter-spacing:-.02em;}
[data-testid="stMetricValue"] > div {white-space:nowrap;}
h1,h2,h3 {color:#162e55;letter-spacing:-.025em;font-weight:800;}
h1 {font-size:2.2rem !important;}
[data-testid="stSidebar"] h2 {color:#183451;}
.stButton button[kind="primary"] {background:#ca7045;}
div[data-testid="stVerticalBlock"] {row-gap:0.9rem;}
</style>""", unsafe_allow_html=True)

PINK = "#ca7045"  # Warm orange accent, paired with the navy / light-blue dashboard
PAGES = ["Tổng quan", "Sản phẩm & thị trường", "Khách hàng & đơn hàng", "Khám phá OLAP", "Dự báo doanh thu", "Hỏi đáp dữ liệu"]
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


def style_pie_percent(fig, height=310):
    """All dashboard pies show their actual percentage labels, not hover-only."""
    fig.update_traces(
        texttemplate="%{percent}", textposition="outside", automargin=True,
        textfont=dict(size=14, family="Nunito, Segoe UI, sans-serif"),
        hovertemplate="<b>%{label}</b><br>Giá trị: %{value:,.2f}<br>Tỷ trọng: %{percent}<extra></extra>",
        sort=False
    )
    fig.update_layout(
        height=height, font=dict(family="Nunito, Segoe UI, sans-serif"),
        paper_bgcolor="#fffdf9", plot_bgcolor="#fffdf9",
        margin=dict(l=20, r=20, t=14, b=45),
        uniformtext_mode="show",
        legend=dict(orientation="h", y=-0.15, x=0, title_text="")
    )
    return fig


def donut_with_percent(frame, names_col, values_col, height=310):
    """The same labeled Plotly donut for every market/category/segment view."""
    fig = px.pie(
        frame, names=names_col, values=values_col, hole=0.44,
        color_discrete_sequence=["#c7794b", "#80acd2", "#243f75",
                                 "#deb97e", "#5b9a9d", "#7774a0", "#d39a9b"]
    )
    return style_pie_percent(fig, height=height)


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
        color=alt.condition(alt.datum[measure] < 0, alt.value("#a94b34"), alt.value(PINK)),
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
        color=alt.Color("series:N", title=None, scale=alt.Scale(range=[PINK, "#5e6472", "#b7d4e4"])),
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
    st.markdown("#### Cơ cấu doanh thu và lợi nhuận")
    category_summary = olap("09_market_category_cube", filters)
    category_summary = category_summary.loc[category_summary.grouping_level.eq(2)].copy()
    if not category_summary.empty:
        category_summary["share"] = 100 * category_summary.sales / category_summary.sales.sum()
        k1, k2 = st.columns(2)
        with k1:
            st.caption("Tỷ trọng doanh thu theo ngành hàng")
            st.plotly_chart(
                donut_with_percent(category_summary, "category", "sales", height=280),
                use_container_width=True, key="category_sales_donut"
            )
        with k2:
            bar(category_summary, "category", "profit", limit=3)
    st.markdown("#### Phân khúc và thị trường nổi bật")
    seg = olap("06_customer_segments", filters)
    regional = olap("05_geography", filters)
    sub = olap("04_product_drilldown", filters)
    r1, r2, r3 = st.columns(3)
    with r1:
        st.caption("Tỷ trọng doanh thu theo phân khúc")
        st.plotly_chart(donut_with_percent(seg, "segment", "sales", height=280),
                        use_container_width=True, key="overview_segment_donut")
    with r2:
        st.caption("Doanh thu theo thị trường")
        market_totals = regional.groupby("market", as_index=False)[["sales","profit"]].sum()
        bar(market_totals, "market", "sales", limit=7)
    with r3:
        st.caption("Top phân nhóm theo lợi nhuận")
        sub = sub.loc[sub.sub_category.notna() & sub.category.notna()].copy()
        bar(sub, "sub_category", "profit", limit=7)

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
    # The year selector refines only this heatmap, within the global date range.
    last_included = (pd.Timestamp(filters[1]) - pd.Timedelta(days=1)).year
    years = list(range(filters[0].year, last_included + 1))
    selected_year = st.selectbox(
        "Năm phân tích Heatmap",
        ["Toàn giai đoạn", *years],
        key="heatmap_year",
        help="Chỉ áp dụng cho Heatmap; vẫn tuân theo khoảng tháng và các bộ lọc thị trường, sản phẩm bên trái."
    )
    heat_filters = filters
    if selected_year != "Toàn giai đoạn":
        start_year = pd.Timestamp(year=selected_year, month=1, day=1).date()
        end_year = pd.Timestamp(year=selected_year + 1, month=1, day=1).date()
        heat_filters = (max(filters[0], start_year), min(filters[1], end_year),
                        filters[2], filters[3])
    cube = olap("09_market_category_cube", heat_filters)
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
        st.caption("Mỗi ô = SUM(profit) / SUM(sales) × 100%; chỉ dùng dòng chi tiết CUBE (grouping_level = 0). "
                   "Bộ lọc năm chỉ áp dụng cho Heatmap và giao với khoảng thời gian ở thanh bên trái.")
    st.subheader("Boxplot doanh thu theo thị trường và ngành hàng")
    box_lines = sales_lines(filters)
    if box_lines.empty:
        st.info("Không có dữ liệu để vẽ boxplot trong phạm vi đã chọn.")
    else:
        box_mode = st.radio(
            "Cấp độ phân tích Boxplot",
            ["Theo thị trường", "Theo ngành hàng", "Theo thị trường và ngành hàng"],
            horizontal=True, key="sales_boxplot_mode"
        )
        if box_mode == "Theo thị trường":
            dimension, color = "market", "market"
        elif box_mode == "Theo ngành hàng":
            dimension, color = "category", "category"
        else:
            dimension, color = "market", "category"
        box_fig = px.box(
            box_lines, x=dimension, y="sales", color=color, points="outliers",
            labels={"sales": "Doanh thu mỗi dòng bán hàng", "market": "Thị trường",
                    "category": "Ngành hàng"},
            color_discrete_sequence=["#c7794b", "#80acd2", "#243f75", "#deb97e",
                                     "#5b9a9d", "#7774a0", "#d39a9b"]
        )
        box_fig.update_layout(
            height=440, paper_bgcolor="#fffdf9", plot_bgcolor="#fffdf9",
            font=dict(family="Nunito, Segoe UI, sans-serif"),
            margin=dict(l=12, r=10, t=20, b=15), legend_title_text="",
            xaxis_title="", yaxis_title="Doanh thu mỗi dòng bán hàng"
        )
        st.plotly_chart(box_fig, use_container_width=True, key="sales_market_boxplot")
        st.caption("Boxplot biểu diễn phân phối doanh thu trên từng dòng giao dịch, "
                   "không phải doanh thu tổng của mỗi thị trường. Đường giữa: trung vị; "
                   "hộp: Q1–Q3; các điểm nằm ngoài râu là ngoại lệ theo quy tắc 1,5×IQR.")
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
    st.subheader("Bản đồ doanh thu và biên lợi nhuận theo địa lý")
    map_metric = st.radio("Chỉ tiêu bản đồ", ["Doanh thu", "Biên lợi nhuận (%)"], horizontal=True, key="geo_map_metric")
    geography_level = st.radio("Phạm vi bản đồ", ["Thế giới (quốc gia)", "Hoa Kỳ (tiểu bang)"],
                              horizontal=True, key="geo_map_level")
    if geography_level == "Thế giới (quốc gia)":
        mapped = countries.copy()
        mapped["margin_pct"] = (100 * mapped.profit / mapped.sales.where(mapped.sales.ne(0)))
        mapped["metric"] = mapped.sales if map_metric == "Doanh thu" else mapped.margin_pct
        fig = px.choropleth(mapped, locations="country", locationmode="country names",
                            color="metric", hover_name="country", hover_data={"sales": ":,.2f", "profit": ":,.2f",
                            "margin_pct": ":.2f", "metric": False, "country": False},
                            color_continuous_scale="YlOrBr" if map_metric == "Doanh thu" else "RdBu",
                            color_continuous_midpoint=0 if map_metric != "Doanh thu" else None,
                            labels={"metric": map_metric}, projection="natural earth")
        fig.update_geos(showcoastlines=False, showcountries=True)
    else:
        state_frame = state_sales(filters)
        state_codes = {
            "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA",
            "Colorado":"CO","Connecticut":"CT","Delaware":"DE","District of Columbia":"DC",
            "Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL",
            "Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
            "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI",
            "Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT",
            "Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ",
            "New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND",
            "Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA",
            "Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
            "Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT",
            "Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI",
            "Wyoming":"WY"
        }
        state_frame["code"] = state_frame.state.map(state_codes)
        state_frame = state_frame.dropna(subset=["code"])
        if state_frame.empty:
            st.info("Không có giao dịch tại Hoa Kỳ trong phạm vi bộ lọc.")
        else:
            state_frame["margin_pct"] = (100 * state_frame.profit / state_frame.sales.where(state_frame.sales.ne(0)))
            state_frame["metric"] = state_frame.sales if map_metric == "Doanh thu" else state_frame.margin_pct
            fig = px.choropleth(state_frame, locations="code", locationmode="USA-states",
                                scope="usa", color="metric", hover_name="state",
                                hover_data={"sales": ":,.2f", "profit": ":,.2f", "margin_pct": ":.2f",
                                            "metric": False, "code": False},
                                color_continuous_scale="YlOrBr" if map_metric == "Doanh thu" else "RdBu",
                                color_continuous_midpoint=0 if map_metric != "Doanh thu" else None,
                                labels={"metric": map_metric})
    if geography_level == "Thế giới (quốc gia)" or not state_frame.empty:
        fig.update_layout(height=450, margin=dict(l=5,r=5,t=10,b=5),
                          paper_bgcolor="#fffdf9", geo=dict(bgcolor="#fffdf9"),
                          coloraxis_colorbar=dict(title=map_metric))
        st.plotly_chart(fig, use_container_width=True, key="sales_geography_map")
    st.caption("Bản đồ sử dụng dữ liệu Global Superstore giai đoạn 2011–2014, không phải 2021–2024. "
               "Lợi nhuận và biên lợi nhuận được tổng hợp theo địa bàn; không suy diễn nguyên nhân.")
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
    st.subheader("Phân khúc khách hàng và hành vi mua sắm")
    orders = customer_orders(filters)
    lookback = st.selectbox("Khoảng thời gian phân tích hành vi khách hàng", [3, 6, 12],
                           index=2, format_func=lambda n: f"{n} tháng", key="customer_lookback")
    window_start, window_end = customer_window(filters[0], filters[1], lookback)
    kpis = customer_kpis(orders, window_start, window_end, lookback)
    st.caption(f"KPI và phân khúc khách hàng trong kỳ "
               f"{pd.Timestamp(window_start):%m/%Y} – "
               f"{(pd.Timestamp(window_end) - pd.Timedelta(days=1)):%m/%Y}; "
               "lịch sử trước kỳ chỉ dùng để nhận diện khách hàng đã từng mua.")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Khách hàng hoạt động", number(kpis["active"]))
    k2.metric("Khách hàng mới", number(kpis["new"]))
    k3.metric("Khách hàng quay lại", number(kpis["returning"]))
    k4.metric("Tỷ lệ khách hàng quay lại", number(kpis["returning_pct"], 2) + "%")
    st.caption("Khách mới = lần đầu xuất hiện trong lịch sử giao dịch quan sát và mua trong kỳ. "
               "Khách quay lại = đã mua trước kỳ và tiếp tục mua trong kỳ. "
               "Tỷ lệ khách quay lại = khách quay lại / khách hoạt động × 100%. "
               "Khách mới ở đầu năm 2011 có thể đã mua trước thời gian dữ liệu ghi nhận.")
    p, q = st.columns(2)
    p.metric(f"Khách không hoạt động trong kỳ {lookback} tháng", f'{number(kpis["inactive"])} / {number(kpis["previous"])}')
    q.metric("Tỷ lệ không hoạt động (đại diện churn)", number(kpis["inactive_pct"], 2) + "%")
    st.caption("Khách không hoạt động = khách từng mua trước kỳ nhưng không có giao dịch trong kỳ; "
               "mẫu số là những khách đã mua trước kỳ. Đây chỉ là đại diện churn, không xác nhận "
               "khách thực sự rời bỏ. Tất cả kết quả chịu giới hạn lịch sử bắt đầu từ 2011.")
    st.metric("Tỷ lệ mua lặp trong kỳ (từ 2 đơn trở lên)", number(kpis["repeat_pct"], 2) + "%")
    segments = segment_breakdown(orders, window_start, window_end)
    if not segments.empty:
        segments["segment_vi"] = segments.segment.map({
            "Consumer": "Cá nhân (Consumer)", "Corporate": "Doanh nghiệp (Corporate)",
            "Home Office": "Văn phòng tại nhà (Home Office)"
        }).fillna(segments.segment)
        a, b = st.columns(2)
        with a:
            st.markdown("**Cơ cấu khách hàng theo phân khúc**")
            fig_segment = donut_with_percent(
                segments, names_col="segment_vi", values_col="customers", height=345
            )
            st.plotly_chart(fig_segment, use_container_width=True, key="customer_segment_donut")
        with b:
            st.markdown("**Doanh thu và lợi nhuận theo nhóm khách hàng**")
            bar(segments.rename(columns={"segment_vi":"customer_segment"}), "customer_segment", "sales", limit=3)
        st.dataframe(segments[["segment_vi","customers","share_pct","sales","profit"]].rename(columns={
            "segment_vi":"Phân khúc","customers":"Khách hàng","share_pct":"Tỷ trọng (%)",
            "sales":"Doanh thu","profit":"Lợi nhuận"}), hide_index=True, width="stretch")
    st.caption("Các phân khúc trong dữ liệu gốc là Consumer, Corporate và Home Office. Không tự gán Home Office thành khách hàng khác.")

    st.subheader("Khách hàng, đơn hàng và vận chuyển")
    top = olap("07_top_customers", filters)
    table(top, "top_customers", "Top 20 khách hàng theo lợi nhuận")
    shipping = olap("08_order_shipping", filters)
    left, right = st.columns(2)
    with left:
        st.markdown("**Chi phí vận chuyển theo phương thức**")
        bar(shipping.groupby("ship_mode", as_index=False)[["sales","profit","shipping_cost"]].sum(),
            "ship_mode", "shipping_cost")
    with right:
        st.markdown("**Doanh thu theo phương thức vận chuyển**")
        bar(shipping.groupby("ship_mode", as_index=False)[["sales","profit"]].sum(), "ship_mode", "sales")
    table(shipping, "order_shipping", "Chi tiết vận chuyển và ưu tiên đơn")

    st.subheader("Rủi ro lợi nhuận theo mức chiết khấu")
    discount = olap("12_discount_analysis", filters).copy()
    discount["loss_rate_pct"] = (100 * discount.loss_lines /
                                 discount.sales_lines.where(discount.sales_lines.ne(0))).fillna(0)
    d1, d2 = st.columns(2)
    with d1:
        bar(discount, "discount_band", "profit", limit=10)
    with d2:
        risk = alt.Chart(discount).mark_bar(color="#ca7045").encode(
            x=alt.X("discount_band:N", title="Mức chiết khấu", sort=None),
            y=alt.Y("loss_rate_pct:Q", title="Tỷ lệ dòng lỗ (%)", scale=alt.Scale(domain=[0,100])),
            tooltip=["discount_band:N","loss_lines:Q","sales_lines:Q",
                     alt.Tooltip("loss_rate_pct:Q", title="Tỷ lệ dòng lỗ (%)", format=".2f")]
        ).properties(height=270)
        st.altair_chart(risk, width="stretch")
    st.dataframe(discount[["discount_band","sales_lines","loss_lines","loss_rate_pct",
                            "sales","profit"]].rename(columns={
        "discount_band":"Mức chiết khấu","sales_lines":"Số dòng bán hàng",
        "loss_lines":"Số dòng lỗ","loss_rate_pct":"Tỷ lệ dòng lỗ (%)",
        "sales":"Doanh thu","profit":"Lợi nhuận"
    }), width="stretch", hide_index=True)
    st.caption("Tỷ lệ dòng lỗ = số dòng có profit < 0 / số dòng bán hàng × 100%. "
               "Mối liên hệ giữa chiết khấu và lợi nhuận là quan sát lịch sử, không chứng minh quan hệ nhân quả.")
    table(discount, "discount_analysis", "Chi tiết các mức chiết khấu")

    st.subheader("Ma trận tương quan các chỉ tiêu kinh doanh")
    lines_data = sales_lines(filters)
    corr_scope_name = st.selectbox(
        "Chọn nhóm để phân tích ma trận",
        list(CORRELATION_SCOPES), key="corr_scope"
    )
    corr_scope = CORRELATION_SCOPES[corr_scope_name]
    corr, observations, country_count = correlation_matrix(lines_data, scope=corr_scope)
    st.caption(f"Nhóm **{corr_scope_name}**: {number(observations)} dòng bán hàng tại "
               f"{number(country_count)} quốc gia trong phạm vi bộ lọc hiện tại. "
               "Quốc gia sinh lời có tổng lợi nhuận > 0; không sinh lời có tổng lợi nhuận ≤ 0.")
    if corr_scope in ("discount_below_10", "discount_above_10"):
        st.caption("Dưới 10% nghĩa là discount < 10%; trên 10% nghĩa là discount > 10%. "
                   "Các giao dịch có chiết khấu đúng 10% không nằm trong hai nhóm này.")
    if corr.empty or corr.isna().all().all():
        st.info("Không có đủ dữ liệu hoặc độ biến thiên để xây dựng ma trận tương quan.")
    else:
        names = corr.columns.tolist()
        values = corr.to_numpy(dtype=float)
        # Values are calculated on all filtered lines; absent correlations are shown as blank.
        labels = [[f"{v:+.2f}" if pd.notna(v) else "" for v in row] for row in values]
        fig_corr = go.Figure(go.Heatmap(
            x=names, y=names, z=values, zmin=-1, zmax=1, zmid=0,
            colorscale=[[0, "#b84c42"], [0.5, "#faf8f5"], [1, "#243e78"]],
            text=labels, texttemplate="%{text}", textfont={"size": 13},
            hovertemplate="%{y} × %{x}<br>Pearson r = %{z:.3f}<extra></extra>",
            colorbar={"title": "r", "tickvals": [-1,-0.5,0,0.5,1]}
        ))
        fig_corr.update_layout(
            height=630, margin=dict(l=15,r=15,t=35,b=90),
            paper_bgcolor="#fffdf9", plot_bgcolor="#fffdf9",
            font=dict(family="Nunito, Segoe UI, sans-serif", size=13),
            xaxis=dict(side="top", tickangle=-35, automargin=True),
            yaxis=dict(autorange="reversed", automargin=True, scaleanchor="x", scaleratio=1)
        )
        st.plotly_chart(fig_corr, use_container_width=True, key="business_correlation_matrix")
        st.caption("Pearson r từ -1 đến +1: âm là biến động ngược chiều, dương là cùng chiều, "
                   "gần 0 là ít liên hệ tuyến tính. Đơn vị quan sát: từng dòng giao dịch. "
                   "Các tỷ số lợi nhuận/đơn vị và biên lợi nhuận được tạo từ những biến "
                   "khác nên có thể có tương quan mang tính toán học.")
        pairs = [
            ("Doanh thu", "Lợi nhuận"),
            ("Chiết khấu (%)", "Lợi nhuận"),
            ("Chiết khấu (%)", "Biên lợi nhuận (%)"),
            ("Số lượng", "Lợi nhuận/đơn vị"),
            ("Phí vận chuyển", "Doanh thu"),
        ]
        notes = []
        for left_label, right_label in pairs:
            r = corr.loc[left_label, right_label]
            if pd.notna(r):
                strength = ("rất yếu" if abs(r) < 0.2 else "yếu" if abs(r) < 0.4
                            else "trung bình" if abs(r) < 0.6 else "khá mạnh" if abs(r) < 0.8
                            else "mạnh")
                direction = "cùng chiều" if r > 0 else "ngược chiều" if r < 0 else "không có"
                notes.append(f"**{left_label} – {right_label}: r = {r:+.2f}**, "
                             f"liên hệ tuyến tính {direction}, mức {strength}.")
        if notes:
            st.markdown("**Nhận xét các mối tương quan đáng chú ý**")
            for note in notes:
                st.markdown("- " + note)
        if corr_scope in ("non_profitable", "discount_below_10", "discount_above_10"):
            compared_scope = ("profitable" if corr_scope == "non_profitable" else
                              "discount_above_10" if corr_scope == "discount_below_10" else
                              "discount_below_10")
            alt_corr, alt_rows, alt_countries = correlation_matrix(
                lines_data, scope=compared_scope
            )
            if not alt_corr.empty:
                compare_pairs = [
                    ("Chiết khấu (%)", "Biên lợi nhuận (%)"),
                    ("Chiết khấu (%)", "Lợi nhuận"),
                    ("Doanh thu", "Lợi nhuận"),
                    ("Số lượng", "Lợi nhuận/đơn vị"),
                    ("Phí vận chuyển", "Lợi nhuận"),
                ]
                comparison = []
                for a, b in compare_pairs:
                    current_r, other_r = corr.loc[a, b], alt_corr.loc[a, b]
                    if pd.notna(current_r) and pd.notna(other_r):
                        comparison.append({
                            "Cặp chỉ tiêu": a + " – " + b,
                            "r nhóm đang xem": round(current_r, 3),
                            "r nhóm đối chiếu": round(other_r, 3),
                            "Chênh lệch r": round(current_r - other_r, 3),
                        })
                if comparison:
                    st.markdown("**Đối chiếu hệ số giữa hai nhóm**")
                    st.caption(f"Nhóm đối chiếu: {next(k for k, v in CORRELATION_SCOPES.items() if v == compared_scope)} "
                               f"({number(alt_rows)} dòng tại {number(alt_countries)} quốc gia).")
                    st.dataframe(pd.DataFrame(comparison), hide_index=True, use_container_width=True)
                    st.caption("Chênh lệch hệ số r cho thấy mô hình liên hệ có thể khác nhau "
                               "giữa hai nhóm, không phải ước lượng tác động do phân nhóm.")
        st.info("Ma trận giúp xác định mối liên hệ thống kê để ưu tiên phân tích, "
                "**không kết luận các yếu tố là nguyên nhân làm tăng hoặc giảm lợi nhuận**. "
                "Để đánh giá tác động nhân quả cần phương pháp nghiên cứu phù hợp.")
        with st.expander("Xem bảng hệ số tương quan"):
            st.dataframe(corr.round(3), use_container_width=True)
    st.subheader("Biểu đồ phân tán cho từng cặp biến")
    pair_options = {
        "Doanh thu và lợi nhuận": ("sales", "profit"),
        "Chiết khấu và lợi nhuận": ("discount", "profit"),
        "Doanh thu và chiết khấu": ("sales", "discount"),
    }
    choice = st.selectbox("Chọn cặp biến", list(pair_options), key="correlation_pair")
    xcol, ycol = pair_options[choice]
    clean = lines_data[[xcol,ycol,"category","row_id"]].dropna()
    if clean.empty or clean[xcol].nunique() < 2 or clean[ycol].nunique() < 2:
        st.info("Không đủ độ biến thiên để tính tương quan Pearson trong phạm vi đang chọn.")
    else:
        pearson = float(clean[xcol].corr(clean[ycol], method="pearson"))
        st.metric("Hệ số tương quan Pearson (r)", f"{pearson:+.3f}")
        sample = clean.sample(n=min(len(clean), 5000), random_state=2026)
        scatter = alt.Chart(sample).mark_circle(size=35, opacity=0.42).encode(
            x=alt.X(f"{xcol}:Q", title=NAMES.get(xcol, xcol)),
            y=alt.Y(f"{ycol}:Q", title=NAMES.get(ycol, ycol)),
            color=alt.Color("category:N", title="Ngành hàng",
                            scale=alt.Scale(range=["#c7794b", "#80acd2", "#243f75"])),
            tooltip=["row_id:Q","category:N",
                     alt.Tooltip(f"{xcol}:Q", format=",.3f"),
                     alt.Tooltip(f"{ycol}:Q", format=",.3f")]
        ).properties(height=330).interactive()
        st.altair_chart(scatter, width="stretch")
        st.caption(f"Hệ số r tính trên toàn bộ {number(len(clean))} dòng giao dịch lọc; "
                   f"biểu đồ lấy mẫu tối đa 5.000 điểm để hiển thị nhanh. "
                   "Pearson đo tương quan tuyến tính, không chứng minh quan hệ nhân quả; "
                   "dữ liệu có thể có ngoại lệ và biến chiết khấu nhận giá trị rời rạc.")


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
        color=alt.Color("series:N", title=None, scale=alt.Scale(range=["#99bcd3", PINK, "#5e6472"])),
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
        color=alt.condition("datum.down_month", alt.value("#a94b34"), alt.value("#8d9aa8")),
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
    st.markdown("**Nhận xét kết quả chẩn đoán**")
    if pd.notna(wape_down):
        st.write(f"Trong 12 tháng kiểm tra năm 2014 có {len(down)} tháng doanh thu giảm. "
                 f"WAPE ở các tháng đó là {wape_down:.2f}%, so với WAPE toàn kỳ {chosen.wape_pct:.2f}%. "
                 + ("Sai số tương đối cao hơn ở các tháng giảm, nên cần thận trọng khi dùng dự báo để lập kế hoạch."
                    if wape_down > chosen.wape_pct else
                    "Sai số tương đối ở các tháng giảm không cao hơn toàn kỳ trong lần đánh giá này."))
    else:
        st.write("Không có đủ tháng giảm hợp lệ để tính WAPE riêng.")
    st.write(f"Mô hình dự đoán đúng chiều biến động so với tháng liền trước ở {correct}/{len(valid_direction)} "
             "tháng kiểm tra. Sai số âm thể hiện dự báo cao hơn thực tế; cần đánh giá thêm mức độ sai số lớn "
             "trước khi đưa ra quyết định kinh doanh. Các nhận xét chỉ áp dụng cho giai đoạn kiểm tra 2014.")
    with st.expander("Mô hình được xây dựng và đánh giá thế nào?"):
        st.write("Huấn luyện ban đầu: 2011–2012. Chọn mô hình trên 2013, kiểm tra trên 2014. "
                 "Mỗi mốc chỉ dùng dữ liệu trước tháng cần dự báo. Sau đánh giá, huấn luyện lại đến 12/2014 để dự báo 01/2015.")
        st.write("Mô hình đã chọn theo ngành hàng: " + "; ".join(
            str(row.category) + ": " + str(row.model) for row in future.itertuples(index=False)) + ".")
        st.caption("Tên mô hình được đọc từ kết quả thực nghiệm, không cố định trong giao diện.")
        st.write("WAPE càng thấp càng tốt; không phải độ chính xác phân loại. Chỉ có bốn năm lịch sử, "
                 "chưa ước lượng khoảng dự báo. Dự báo doanh thu hỗ trợ lập mục tiêu, chưa xác định được lượng nhập hàng.")
        st.caption("Thời điểm tạo kết quả: " + manifest["created_at"])



def chat_page(filters):
    st.subheader("Trợ lý hỏi đáp Global Superstore")
    st.caption("Khám phá doanh thu, lợi nhuận, sản phẩm, thị trường và khách hàng "
               "từ dữ liệu Global Superstore 2011–2014. Kết quả theo bộ lọc ở thanh bên trái.")
    current_scope = (str(filters[0]), str(filters[1]), filters[2], filters[3])
    if st.session_state.get("chat_scope") != current_scope:
        st.session_state["chat_scope"] = current_scope
        st.session_state["warehouse_chat"] = []
    for item in st.session_state.get("warehouse_chat", []):
        with st.chat_message(item["role"]):
            st.markdown(item["text"])
            if item.get("table") is not None:
                st.dataframe(item["table"], use_container_width=True, hide_index=True)
    prompt = st.chat_input("Hỏi về doanh thu, lợi nhuận, thị trường, khách hàng...", max_chars=400)
    if prompt:
        st.session_state["warehouse_chat"].append({"role": "user", "text": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        response, frame = answer_question(prompt, filters)
        st.session_state["warehouse_chat"].append({
            "role": "assistant", "text": response, "table": frame
        })
        with st.chat_message("assistant"):
            st.markdown(response)
            if frame is not None:
                st.dataframe(frame, use_container_width=True, hide_index=True)


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
        elif page == "Hỏi đáp dữ liệu":
            chat_page(filters)
        else:
            explorer(filters)
    except psycopg.Error:
        st.error("Không thể tải dữ liệu. Kiểm tra PostgreSQL đã chạy và kho đã được nạp; sau đó nhấn Làm mới dữ liệu.")
        st.caption("Khởi động kho: python src/warehouse/setup_local_postgres.py. Cấu hình kết nối qua SUPERSTORE_DATABASE_URL nếu dùng máy chủ khác.")


if __name__ == "__main__":
    main()

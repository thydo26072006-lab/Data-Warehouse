"""Strictly scoped, read-only question answering about this Global Superstore warehouse.

There is deliberately no arbitrary SQL generation and no external LLM API.
Only the supported business questions below map to repository-approved OLAP queries.
"""
import re
import unicodedata

import pandas as pd

from data import metadata, olap
from insights import customer_orders, customer_kpis, sales_lines


EXAMPLES = [
    "Tổng doanh thu và lợi nhuận của Global Superstore là bao nhiêu?",
    "Doanh thu theo ngành hàng năm 2014?",
    "Doanh thu cao nhất ở đâu?",
    "Thị trường nào có lợi nhuận cao nhất?",
    "Top 5 quốc gia có doanh thu cao nhất?",
    "Quốc gia nào có lợi nhuận thấp nhất?",
    "Cơ cấu khách hàng theo phân khúc?",
    "Tỷ lệ khách hàng quay lại là bao nhiêu?",
    "Mức chiết khấu nào có tỷ lệ dòng lỗ cao?",
    "Tương quan giữa doanh thu và lợi nhuận?",
]


def normalize(question):
    raw = unicodedata.normalize("NFD", question.casefold())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return raw.replace("đ", "d")


def fmt(value, digits=2):
    if pd.isna(value):
        return "không có dữ liệu"
    return f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _scope(question, base_filters):
    """Recognize only explicit years inside source data; no dynamic identifiers/SQL."""
    text = normalize(question)
    mentioned_years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)]
    if any(y not in (2011, 2012, 2013, 2014) for y in mentioned_years):
        return None, "Dữ liệu bán hàng của nhóm chỉ gồm giai đoạn 2011–2014. Mình không có dữ liệu thực tế cho năm ngoài khoảng này."
    if len(set(mentioned_years)) > 1:
        return None, "Hiện chatbot chỉ nhận một năm cụ thể trong mỗi câu hỏi. Bạn có thể chọn một năm hoặc dùng bộ lọc chung."
    if not mentioned_years:
        return base_filters, None
    year = mentioned_years[0]
    start = max(base_filters[0], pd.Timestamp(year=year, month=1, day=1).date())
    end = min(base_filters[1], pd.Timestamp(year=year + 1, month=1, day=1).date())
    if start >= end:
        return None, "Năm bạn hỏi nằm ngoài khoảng tháng đang được chọn. Hãy điều chỉnh bộ lọc ở thanh bên trái."
    return (start, end, base_filters[2], base_filters[3]), None


def _unsupported():
    return ("Mình chỉ trả lời các câu hỏi dựa trên dữ liệu Global Superstore của nhóm "
            "(2011–2014): doanh thu, lợi nhuận, sản phẩm, thị trường, quốc gia, "
            "phân khúc khách hàng, chiết khấu và tương quan. "
            "Mình không có dữ liệu để trả lời câu hỏi này. "
            "Bạn có thể chọn một câu hỏi mẫu ở bên dưới.")


def answer_question(question, base_filters):
    """Return (response: str, table: DataFrame | None)."""
    if not question or len(question.strip()) < 3 or len(question) > 400:
        return "Vui lòng nhập câu hỏi cụ thể, dài tối đa 400 ký tự.", None
    filters, error = _scope(question, base_filters)
    if error:
        return error, None
    q = normalize(question)
    if any(word in q for word in ("bo qua", "ignore", "password", "mat khau", "secret",
                                   "api key", "token", "drop table", "delete from", "insert into",
                                   "update dw", "system prompt", "lap trinh", "thoi tiet",
                                   "chinh tri", "tong thong", "bong da", "tin tuc")):
        return _unsupported(), None

    def contains(*terms):
        return any(term in q for term in terms)

    span = f"{filters[0].strftime('%d/%m/%Y')}–{(pd.Timestamp(filters[1]) - pd.Timedelta(days=1)).strftime('%d/%m/%Y')}"
    profit = contains("loi nhuan", "profit", "sinh loi")
    discount = contains("chiet khau", "discount")
    customers = contains("khach hang", "customer", "phan khuc", "segment")
    # Location questions precede general KPI totals.
    # Without a specified level, "ở đâu" uses country; explicit market uses markets.
    market = contains("thi truong", "market", "khu vuc", "region", "vung nao")
    where = contains("o dau", "noi nao", "cho nao", "tai dau", "dia diem nao",
                     "where", "o quoc gia nao", "o nuoc nao")
    country = contains("quoc gia", "nuoc nao", "country") or (where and not market)
    category = contains("nganh hang", "danh muc", "nhom san pham", "category", "san pham", "product")
    sales = contains("doanh thu", "sales", "ban hang")
    correlation = contains("tuong quan", "correlation", "pearson", "moi quan he")
    ratio = contains("ty le", "ti le", "bao nhieu phan tram")
    sort_low = contains("thap nhat", "it nhat", "kem nhat", "thua lo", "lo nhat")
    sort_high = contains("cao nhat", "nhieu nhat", "lon nhat", "top ", "hang dau")
    n_match = re.search(r"top\s*(\d+)", q)
    limit = min(max(int(n_match.group(1)), 1), 15) if n_match else 5

    if contains("du bao", "forecast", "2015"):
        return ("Mô hình dự báo có trong trang **Dự báo doanh thu**. Chatbot hiện chỉ trả lời "
                "số liệu giao dịch quan sát 2011–2014; vui lòng mở trang dự báo để xem "
                "dự báo và các chỉ số WAPE, MAE, RMSE."), None

    if correlation:
        pairs = [("sales", "profit", "doanh thu – lợi nhuận"),
                 ("discount", "profit", "chiết khấu – lợi nhuận"),
                 ("sales", "discount", "doanh thu – chiết khấu")]
        if discount and sales and not profit:
            x, y, name = pairs[2]
        elif discount and profit:
            x, y, name = pairs[1]
        elif sales and profit:
            x, y, name = pairs[0]
        else:
            return ("Hãy chỉ rõ cặp biến: **doanh thu và lợi nhuận**, "
                    "**chiết khấu và lợi nhuận**, hoặc **doanh thu và chiết khấu**."), None
        rows = sales_lines(filters)
        frame = rows[[x, y]].dropna()
        if frame.empty or frame[x].nunique() < 2 or frame[y].nunique() < 2:
            return f"Không đủ dữ liệu để tính tương quan {name} trong phạm vi đã chọn.", None
        r = frame[x].corr(frame[y])
        return (f"Tương quan Pearson giữa **{name}** trong giai đoạn {span}: "
                f"**r = {fmt(r, 3)}** (tính trên {fmt(len(frame), 0)} dòng giao dịch). "
                "Hệ số này đo liên hệ tuyến tính, không chứng minh quan hệ nhân quả."), None

    if discount:
        frame = olap("12_discount_analysis", filters).copy()
        if frame.empty:
            return "Không có dữ liệu chiết khấu trong phạm vi này.", None
        frame["loss_pct"] = (100 * frame.loss_lines / frame.sales_lines.where(frame.sales_lines.ne(0))).fillna(0)
        columns = frame[["discount_band", "sales_lines", "loss_lines", "loss_pct", "profit"]]
        maxrow = frame.loc[frame.loss_pct.idxmax()]
        return (f"Trong giai đoạn {span}, nhóm chiết khấu có tỷ lệ dòng lỗ cao nhất là "
                f"**{maxrow.discount_band}**, với **{fmt(maxrow.loss_pct)}%** dòng bán hàng có lợi nhuận âm. "
                "Tỷ lệ dòng lỗ = số dòng profit < 0 / tổng số dòng × 100%; "
                "đây là quan sát, không chứng minh chiết khấu gây lỗ."), columns

    if customers and contains("quay lai", "mua lai", "tro lai", "moi", "roi bo", "khong hoat dong"):
        orders = customer_orders(filters)
        k = customer_kpis(orders, filters[0], filters[1], 12)
        return (f"Trong giai đoạn {span}, có **{fmt(k['active'], 0)}** khách hàng hoạt động, "
                f"**{fmt(k['new'], 0)}** khách hàng mới và "
                f"**{fmt(k['returning'], 0)}** khách hàng quay lại "
                f"(**{fmt(k['returning_pct'])}%** khách hoạt động). "
                f"Khách không hoạt động theo cửa sổ 12 tháng: "
                f"**{fmt(k['inactive'], 0)}/{fmt(k['previous'], 0)}** "
                f"(**{fmt(k['inactive_pct'])}%**). Đây chỉ là chỉ số đại diện, "
                "không xác nhận khách thực sự rời bỏ."), None

    if customers:
        frame = olap("06_customer_segments", filters)
        if frame.empty:
            return "Không có phân khúc khách hàng trong phạm vi đã chọn.", None
        frame = frame.copy()
        frame["share_pct"] = 100 * frame.customers / frame.customers.sum()
        return (f"Phân khúc khách hàng trong giai đoạn {span} gồm **Consumer (cá nhân)**, "
                "**Corporate (doanh nghiệp)** và **Home Office (văn phòng tại nhà)**. "
                "Bảng dưới đây thể hiện số khách và tỷ trọng theo số khách phân biệt."), frame[["segment", "customers", "share_pct", "sales", "profit"]]

    if country:
        frame = olap("05_geography", filters).groupby("country", as_index=False)[["sales", "profit"]].sum()
        if frame.empty:
            return "Không có dữ liệu quốc gia trong phạm vi đã chọn.", None
        key = "profit" if profit else "sales"
        ascending = sort_low
        frame = frame.sort_values(key, ascending=ascending).head(limit)
        row = frame.iloc[0]
        return (f"Trong giai đoạn {span}, quốc gia "
                f"{'có '+('lợi nhuận' if profit else 'doanh thu')+' thấp nhất' if sort_low else 'đứng đầu theo '+('lợi nhuận' if profit else 'doanh thu')} "
                f"là **{row.country}** ({fmt(row[key])}). Bảng hiển thị {len(frame)} quốc gia."), frame

    if market:
        frame = olap("09_market_category_cube", filters)
        frame = frame.loc[frame.grouping_level.eq(1), ["market", "sales", "profit"]]
        if frame.empty:
            return "Không có dữ liệu thị trường trong phạm vi đã chọn.", None
        key = "profit" if profit else "sales"
        frame = frame.sort_values(key, ascending=sort_low)
        row = frame.iloc[0]
        return (f"Thị trường **{row.market}** {'thấp nhất' if sort_low else 'đứng đầu'} "
                f"theo {'lợi nhuận' if profit else 'doanh thu'} trong giai đoạn {span}: "
                f"**{fmt(row[key])}**. Xem bảng đối chiếu các thị trường bên dưới."), frame

    if category:
        frame = olap("09_market_category_cube", filters)
        frame = frame.loc[frame.grouping_level.eq(2), ["category", "sales", "profit"]]
        if frame.empty:
            return "Không có dữ liệu ngành hàng trong phạm vi đã chọn.", None
        key = "profit" if profit else "sales"
        frame = frame.sort_values(key, ascending=sort_low)
        row = frame.iloc[0]
        return (f"Ngành hàng **{row.category}** {'thấp nhất' if sort_low else 'đứng đầu'} "
                f"theo {'lợi nhuận' if profit else 'doanh thu'} trong giai đoạn {span}: "
                f"**{fmt(row[key])}**. Bảng dưới đây cho biết cả doanh thu và lợi nhuận."), frame

    if sales or profit or contains("tong quan", "tong so don", "so don", "so luong"):
        row = olap("01_overview", filters).iloc[0]
        return (f"Tổng quan Global Superstore trong giai đoạn **{span}** theo bộ lọc hiện tại: "
                f"**doanh thu {fmt(row.sales)}**, **lợi nhuận {fmt(row.profit)}**, "
                f"**{fmt(row.order_groups, 0)} đơn hàng**, "
                f"**{fmt(row.quantity, 0)} sản phẩm được bán**. "
                "Đơn hàng được xác định theo mã đơn + ngày đặt + mã khách hàng."), None

    return _unsupported(), None

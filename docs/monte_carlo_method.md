# Monte Carlo cho dự báo doanh thu Global Superstore

## Mục tiêu
Bổ sung một phân tích bất định cho dự báo doanh thu tháng 01/2015 đã có.
Không thay mô hình Holt–Winters / seasonal naive đã lựa chọn, không thay các
chỉ số WAPE, MAE, RMSE của bài đánh giá dự báo điểm.

## Phương pháp đã triển khai
- Dự báo điểm theo từng nhóm hàng là kết quả của quy trình huấn luyện/đánh giá hiện tại.
- Tập sai số hiệu chỉnh: 12 dự báo một bước trước của mô hình **selected**, tháng 01–12/2014;
  mỗi sai số được định nghĩa: doanh thu thực tế trừ doanh thu dự báo.
- Lấy mẫu lại có hoàn lại 10.000 lần (có thể chỉnh 1.000–30.000 và đổi seed).
- Khi xét tổng doanh thu, lấy **cùng một tháng** cho cả ba ngành hàng trong
  mỗi lần mô phỏng để giữ lại sự phụ thuộc giữa sai số theo ngành.
- Doanh thu mỗi ngành được chặn ở 0 trước khi tính tổng.
- Kết quả: P5, P50, P95, phân phối thực nghiệm và tỷ lệ kịch bản có doanh thu
  **nhỏ hơn** mục tiêu do người dùng đặt.

Công thức:

    doanh_thu_kich_ban_nganh = max(0, du_bao_diem_nganh + sai_so_2014_duoc_lay_mau)
    doanh_thu_kich_ban_tong = sum(doanh_thu_kich_ban_nganh)
    xac_suat_duoi_muc_tieu = so_kich_ban_duoi_muc_tieu / tong_so_kich_ban

## Giới hạn bắt buộc nêu trong báo cáo
- Bộ dữ liệu có 48 tháng (2011–2014); sai số dùng cho mô phỏng chỉ có 12 tháng
  kiểm tra trong 2014. Dù mô phỏng 10.000 lần, chỉ có **tối đa 12 tổ hợp sai số**
  theo tháng và không bổ sung quan sát thực tế.
- Sai số 2014 vừa là cơ sở hiệu chỉnh Monte Carlo, nên P5–P95 **không phải**
  khoảng dự báo có độ phủ độc lập đã được kiểm định. Chưa có phép đánh giá độ
  phủ ngoài mẫu dành riêng cho khoảng dự báo.
- Giả định phân phối sai số 2014 đại diện cho 01/2015, chưa tính rủi ro thay đổi
  cơ cấu thị trường, đứt gãy xu hướng hay bất định của việc ước lượng tham số.
- Tỷ lệ mô phỏng dưới mục tiêu là ước lượng phụ thuộc giả định, không phải cam
  kết doanh thu và không thay thế quyết định kinh doanh dựa trên thông tin thực tế.
- Không gọi mô phỏng là cải thiện độ chính xác WAPE/MAE/RMSE của dự báo điểm.

## Vị trí và cách sử dụng
Trang Streamlit: **Dự báo doanh thu** → **Mô phỏng Monte Carlo: phân phối doanh thu dự báo**.
Chọn toàn bộ doanh thu hoặc một ngành ở mục Phạm vi dự báo phía trên, sau đó
điều chỉnh số lượt mô phỏng, seed và mục tiêu doanh thu.

## Kiểm thử
Chạy kiểm thử thuật toán không cần kết nối kho dữ liệu:

    python -m unittest discover -s src/dashboard -p 'test_monte_carlo.py' -v

Kiểm thử giao diện tích hợp (cần cấu hình PostgreSQL và dữ liệu kho):

    python src/dashboard/check_dashboard.py

Không có kết quả Monte Carlo cố định được lưu đè lên bộ dự báo gốc.

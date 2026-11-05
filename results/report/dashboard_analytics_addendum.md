# Bổ sung phân tích Dashboard và gợi ý cập nhật Chương 4–7

Bản cập nhật ngày 04/11/2026 trên nhánh `import/btl-khodl`. Tất cả số liệu phải đọc trực tiếp từ `dw.v_sales_analysis` hoặc file dự báo đã kiểm định; không sử dụng các giá trị 2021–2024 trong hình mẫu (dữ liệu Global Superstore của nhóm: 2011–2014).

## Phân tích rủi ro theo mức chiết khấu (đề nghị đặt trong 4.4.2)

SQL OLAP 12 đã trả về `sales_lines`, `loss_lines`, `sales` và `profit` theo khoảng chiết khấu. Dashboard hiển thị thêm biểu đồ và bảng `loss_rate_pct = 100 * loss_lines / sales_lines`. Diễn giải nên nêu tỷ trọng dòng lỗ trong nhóm chiết khấu >40% khi đã xác nhận giá trị thực tế trên Dashboard; đối chiếu doanh thu và tổng lợi nhuận ở cùng nhóm. Không suy luận quan hệ nhân quả chỉ từ tương quan.

**Minh chứng cần chụp:** Trang Khách hàng & đơn hàng → "Rủi ro lợi nhuận theo mức chiết khấu"; ảnh bao gồm cả biểu đồ tỷ lệ dòng lỗ và bảng có `sales_lines`, `loss_lines`.

## Chẩn đoán mô hình dự báo năm 2014 (đề nghị đặt trong 4.5)

Dashboard giữ các chỉ tiêu đã công bố (MAE, RMSE, WAPE), bổ sung:
- Sai số `actual - predicted` theo tháng trong 2014. Dấu âm: dự báo cao hơn thực tế.
- WAPE riêng các tháng doanh thu thực tế giảm so với tháng trước, chỉ dùng để **chẩn đoán sau đánh giá**, không được dùng để lựa chọn mô hình khi tạo dự báo.
- Số tháng đúng hướng tăng/giảm so với doanh thu tháng liền trước.
- Bảng năm tháng có sai số tuyệt đối lớn nhất.
- Đoạn nhận xét tự động so sánh WAPE tháng giảm với WAPE toàn kỳ.

**Minh chứng:** Trang Dự báo doanh thu → "Chẩn đoán sai số dự báo năm 2014", chụp đủ biểu đồ sai số, KPI, đoạn nhận xét và bảng sai số lớn.

## Phân tích khách hàng (bổ sung mục phân tích hành vi)

Nguồn: dữ liệu đơn hàng được gom theo khóa `customer_id + order_id + order_date` từ PostgreSQL, truy hồi lịch sử quan sát đến cuối kỳ được chọn, và chịu bộ lọc ngành hàng/thị trường.

- **Khách hoạt động:** có ít nhất một đơn trong khoảng tháng được chọn.
- **Khách mới:** khách hoạt động có ngày mua đầu tiên *trong phạm vi dữ liệu và bộ lọc đang chọn* thuộc khoảng phân tích.
- **Khách quay lại:** khách hoạt động đã có giao dịch trước ngày đầu kỳ.
- **Tỷ lệ mua lặp:** số khách hoạt động có ít nhất hai đơn hàng phân biệt tính đến cuối kỳ / số khách hoạt động.
- **Không hoạt động (churn proxy):** khách mua trước thời điểm `cuối kỳ - N tháng` nhưng không phát sinh đơn nào trong N tháng trước cuối kỳ, chia cho số khách từng mua trước mốc đó. Lựa chọn N=3,6,12. **Không phải churn thực sự** do dữ liệu không có sự kiện rời bỏ, và kết quả chịu giới hạn quan sát trái ở năm 2011.
- **Phân khúc:** Consumer (cá nhân), Corporate (doanh nghiệp), Home Office (văn phòng tại nhà); tỷ trọng là tỷ lệ số khách *phân biệt* trong kỳ theo từng phân khúc.

**Minh chứng:** Trang Khách hàng & đơn hàng, ảnh nhóm KPI, biểu đồ phân khúc và thay đổi bộ lọc N tháng.

## Phân tích tương quan

Tính Pearson trên **toàn bộ dòng giao dịch được lọc** từ PostgreSQL, gồm các cặp doanh thu–lợi nhuận, chiết khấu–lợi nhuận, doanh thu–chiết khấu. Biểu đồ phân tán chỉ hiển thị mẫu cố định tối đa 5.000 điểm nhằm giữ hiệu năng; hệ số được tính trên toàn bộ dữ liệu, không phải mẫu. Không diễn giải `r` thành tác động nhân quả hoặc tỷ lệ phần trăm.

## Địa lý và giao diện

Giao diện sáng xanh/kem với điểm nhấn cam, thẻ KPI và cụm biểu đồ overview, không sử dụng màu hoặc số liệu 2021–2024 từ ảnh tham khảo. Trang Sản phẩm & thị trường có:
- Choropleth **thế giới theo quốc gia**, chọn doanh thu hoặc biên lợi nhuận.
- Choropleth **Hoa Kỳ theo tiểu bang** từ tên tiểu bang của dữ liệu gốc; chỉ những tiểu bang có dòng giao dịch trong phạm vi lọc mới được tô.
- Heatmap 3 ngành hàng × 7 thị trường, chọn năm 2011–2014 hoặc toàn giai đoạn.
- Drill-down và Bottom 10 quốc gia được giữ lại.

Bản đồ dùng Plotly, yêu cầu cài phiên bản mới của `src/dashboard/requirements.txt` (đã thêm plotly). Nếu môi trường trình duyệt không truy cập được bản đồ nền, kiểm tra Internet và các chính sách truy cập tài nguyên bản đồ; bảng số liệu theo địa lý vẫn có thể xem trong ứng dụng.

## Kiểm thử và tính nhất quán

Các truy vấn mới chỉ đọc dữ liệu, không thay đổi bảng Star Schema, ETL, 12 SQL OLAP gốc hay tập dự báo. `check_dashboard.py` trên GitHub đã bổ sung kiểm tra khách hàng, phân khúc, dòng giao dịch và tổng doanh thu tiểu bang. Phải chạy lại trên PostgreSQL thật; kết quả 8/8 PASS cũ không đại diện cho phiên bản vừa cập nhật.

Chương 6 có thể ghi thêm: kiểm thử tính nhất quán số lượng khách mới + quay lại = khách hoạt động; tổng số khách theo phân khúc; tổng doanh thu địa lý Hoa Kỳ; kiểm tra tỷ lệ dòng lỗ trong [0,100%]. Chương 7 nên bàn về giới hạn churn proxy, khác biệt tỷ lệ mua lại giữa phân khúc và không suy ra nhân quả từ tương quan.

# Bằng chứng kiểm thử đối chiếu Chương 6

Bộ bằng chứng mới chạy ngày **15/11/2026**, trên mã nguồn commit
`aa6b8d99dec1cab3250a1a067a2d17ece45d824a` của nhánh `DNNB`, Windows,
Python **3.12.6**, PostgreSQL **17.11** cục bộ. Mã nguồn không được sửa.
`manifest.json` ghi SHA-256 theo byte của mã nguồn, dữ liệu/kết quả đầu vào,
báo cáo và các tệp bằng chứng; không tự ghi hash của chính manifest.

| Mục báo cáo | Bằng chứng | Kết quả |
| --- | --- | --- |
| 6.1, 6.3–6.7 | `dashboard-tests.log`, `dashboard-checks.json` | 21 bài, 0 thất bại, 0 lỗi; 59,336 giây |
| 6.2 | `warehouse-verify.log`, `warehouse-verification.json` | 51.290 dòng, 26 thuộc tính, 6 khóa ngoại; chênh lệch 4 tổng bằng 0 |
| 6.3, 6.7 | `warehouse-integration.log`, `warehouse-integration.json` | 7 kiểm tra: nạp lại, ràng buộc, rollback, 12 truy vấn OLAP |
| 6.4; Bảng 19 | `customer_windows.csv` | Cửa sổ 3/6/12 tháng; hoạt động = mới + quay lại |
| 6.4; phân tích Pearson | `pearson_all.csv`, `pearson_profitable.csv`, `pearson_non_profitable.csv`, `pearson_discount_below_10.csv`, `pearson_discount_above_10.csv` | 5 ma trận 7×7, xuất trực tiếp bằng hàm Dashboard từ kho |
| Môi trường, phạm vi lọc | `environment.json` | Phiên bản thực tế, thời gian chạy kho, số dòng/quốc gia từng nhóm |
| Monte Carlo | `cv04-manifest.json`, `monte-carlo-tests-cv04.log`, `monte-carlo-evaluation.log` | Bằng chứng CV04 có sẵn được giữ nguyên; không gán là lượt chạy mới |

`dashboard-checks.json` là bản sao nguyên byte từ `results/dashboard/checks.json`
do bộ kiểm thử sinh ra. Mảng `coverage` trong JSON là nhãn tóm tắt có sẵn trong
mã nguồn; danh sách test thực tế xem log đầy đủ. Các JSON kho cũng được sao từ
đầu ra thực tế. Log giữ cả cảnh báo Streamlit; cảnh báo không được tính thành lỗi test.

## Chạy lại

Cài các dependency theo tài liệu dự án và cấu hình kết nối kho đã nạp dữ liệu
với `SUPERSTORE_DATABASE_URL`, `PGPASSFILE`, `PSQL_PATH`. Không đưa mật khẩu,
tệp pgpass hoặc khóa API lên Git. Các lệnh chạy từ thư mục gốc repo:

```powershell
python -B src/dashboard/check_dashboard.py
python -B src/warehouse/warehouse.py verify
python -B src/warehouse/check_pipeline.py
```

Lệnh cuối thực hiện nạp lại và thử dữ liệu vi phạm có rollback; dùng kho kiểm thử.
Đầu ra các lệnh nằm dưới `results/`. Trong lần thu thập này, kết quả đầu vào đã
được lưu trong Git được phục hồi nguyên byte sau khi kiểm thử; bản bằng chứng
mới nằm riêng ở `evidence/`.

Các CSV bổ sung dùng `data.metadata()` để lấy toàn bộ thị trường/ngành hàng,
phạm vi `[2011-01-01, 2015-01-01)`. Gọi `insights.customer_orders(filters)`,
`customer_window(start, end, months)` và `customer_kpis(orders, start, end)`
cho từng cửa sổ 3/6/12 tháng. Gọi `sales_lines(filters)` rồi
`correlation_matrix(rows, scope=scope)` cho từng giá trị trong
`CORRELATION_SCOPES`; xuất ma trận bằng `DataFrame.to_csv`. File
`environment.json` ghi rõ bộ lọc và quy mô từng nhóm để đối chiếu.

## Giới hạn và cập nhật báo cáo

Đây là kiểm thử cục bộ bằng PostgreSQL và Streamlit AppTest, không phải nghiệm
thu trình duyệt, Neon, Streamlit Cloud hoặc Gemini với API thật. Dự báo
Holt–Winters được kiểm tra từ kết quả đã lưu, không huấn luyện lại.

`KDL_Main.pdf` chỉ sửa 3 chỗ ngày nghiệm thu từ 14/11/2026 thành 15/11/2026
và phiên bản PostgreSQL từ 18.6 thành 17.11 tại Chương 6 (trang PDF 65 và 70,
tức trang in 57 và 62). Giữ 78 trang và nội dung các trang còn lại.
Không dùng lại các log thất bại hoặc manifest của phiên bản cũ để chứng minh
cho lần nghiệm thu này.

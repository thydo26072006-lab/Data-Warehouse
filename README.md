# Bàn giao CO4031 — Nhóm 5

Đây là bản bàn giao các phần đã làm để thành viên tiếp theo hoàn thiện bộ nộp theo §5.1 của Assignment. Báo cáo chính thức là `KDL_Main.pdf`; mã nguồn lấy từ bản Next_step đã nghiệm thu.

## Thành phần

- `KDL_Main.pdf`: báo cáo hiện tại.
- `src/`: SQL, ETL, notebook khảo sát, dự báo, dashboard, mã kiểm thử và các requirements.
- `data/`: CSV nguồn và CSV processed chính thức, đủ 51.290 dòng.
- `results/forecasting/`: 5 file dashboard cần trực tiếp để hiển thị DSS đã chạy.
- `results/warehouse/olap/`: 12 CSV chuẩn dùng bởi kiểm thử truy vấn/dashboard.
- `.streamlit/config.toml`: cấu hình giao diện; `.gitignore`: loại runtime và cấu hình riêng khi quản lý mã nguồn.

Các kết quả trong `results/` là đầu vào cần thiết cho ứng dụng/kiểm thử, không phải tập log tiến độ. Không kèm môi trường Python, PostgreSQL binaries/data, mật khẩu, cache, Git history, log, file đề xuất hoặc các bản báo cáo trùng.

## Phần đã hoàn thành

Star Schema 1 Fact + 5 Dimension, 6 FK; ETL, nạp lại và rollback; 12 truy vấn OLAP; DSS dự báo Holt–Winters; frontend Streamlit 5 trang. Bản nguồn đã chạy 8 kiểm thử tiền xử lý, 4 kiểm thử dự báo, 8 kiểm thử ứng dụng, kiểm tra Edge và 53 đối soát. Số liệu dự báo làm tròn khớp báo cáo.

## Chạy trên máy người nhận

Yêu cầu Windows x64, Python 3.12 và quyền tải các thư viện/PostgreSQL. Mở PowerShell tại thư mục chứa README này (không chạy từ `src/forecasting`).

```powershell
python -m venv .runtime/forecast-venv
& .runtime/forecast-venv/Scripts/python.exe -m pip install -r src/forecasting/requirements.txt -r src/dashboard/requirements.txt
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/setup_local_postgres.py
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/warehouse.py all
& .runtime/forecast-venv/Scripts/python.exe -m streamlit run src/dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Mở `http://127.0.0.1:8501`. PostgreSQL riêng ở `127.0.0.1:55432`, database `superstore_dw`. Script setup tạo runtime và thông tin kết nối trên máy người nhận; không mang runtime từ máy cũ. Nếu dùng database có sẵn, cấu hình `PSQL_PATH`, `PGPASSFILE`, `SUPERSTORE_DATABASE_URL` tương ứng.

Dữ liệu processed đã có sẵn, không bắt buộc tạo lại. Khi cần tái tạo hoặc huấn luyện lại:

```powershell
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/etl/preprocess.py --check-baseline
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/warehouse.py all
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/forecasting/forecast.py
```

Các lệnh kiểm tra sau khi nạp kho:

```powershell
& .runtime/forecast-venv/Scripts/python.exe -X utf8 -m unittest discover -s src/etl -p test_preprocess.py -v
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/check_pipeline.py
& .runtime/forecast-venv/Scripts/python.exe -X utf8 -m unittest discover -s src/forecasting -p test_forecast.py -v
& .runtime/forecast-venv/Scripts/python.exe -X utf8 src/dashboard/check_dashboard.py
```

Kiểm tra trình duyệt là tùy chọn khi phát triển: cài `src/dashboard/requirements-dev.txt`, chạy Streamlit, rồi chạy `src/dashboard/check_browser.py` với Microsoft Edge đã cài.

## Việc người nhận cần hoàn thiện trước khi nộp

1. Hoàn thiện báo cáo: lời mở đầu còn dang dở; ghi phân vai/sản phẩm của từng thành viên; bổ sung tổng kết/hướng phát triển và ảnh demo phù hợp.
2. **Bổ sung slide thuyết trình dạng PDF** — chưa có trong bộ bàn giao hiện tại, bắt buộc theo §5.1.
3. Nếu nhóm không thuyết trình trực tiếp: chuẩn bị video 10–15 phút có tất cả thành viên, bật quyền xem và ghi link trên bìa báo cáo. Nếu thuyết trình trực tiếp, tất cả thành viên vẫn phải trình bày.
4. Đóng ZIP cuối gồm báo cáo, `src/`, `data/`, slide PDF và link video nếu áp dụng. Giữ các file kết quả cần thiết để chạy dashboard.

Bộ bàn giao hiện tại chưa phải bộ nộp cuối vì chưa có slide PDF và phần thuyết trình chưa được xác nhận. Hạn theo Assignment: 23:59 ngày 15/11/2026, nộp LMS.

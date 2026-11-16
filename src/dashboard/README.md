# Chạy Dashboard trên nhánh DNNB

Đây là hướng dẫn cài đặt được [run_dashboard.ps1](run_dashboard.ps1) dẫn tới
khi chưa có môi trường Python. Xem thêm [README gốc](../../README.md) và
[hướng dẫn chung](../../docs/BTL_KHODL_HUONG_DAN.md).

## Lấy đúng phiên bản

Nếu chưa có repo:

```powershell
git clone --branch DNNB --single-branch https://github.com/thydo26072006-lab/Data-Warehouse.git
cd Data-Warehouse
```

Nếu đã clone repo, lưu hoặc commit công việc đang làm trước khi chuyển nhánh:

```powershell
git fetch origin
git switch DNNB
git pull --ff-only origin DNNB
```

Nếu clone trước đó chỉ lấy một nhánh khác và chưa thấy `origin/DNNB`, chạy
`git fetch origin DNNB:refs/remotes/origin/DNNB` trước `git switch DNNB`.
Nếu dùng ZIP, tải và giải nén toàn bộ nhánh `DNNB` vào thư mục mới; không chạy
các lệnh Git trong thư mục ZIP.

## Windows: PostgreSQL cục bộ của dự án

Dùng Windows x64 và Python 3.12. Mở PowerShell tại **thư mục gốc repo**, nơi
có `README.md`, `src/` và `data/`; không mở tại `src/dashboard` hoặc `docs`.
Cần kết nối mạng ở lần đầu để cài dependency và tải PostgreSQL.

```powershell
py -3.12 -m venv .runtime/forecast-venv
& ./.runtime/forecast-venv/Scripts/python.exe -m pip install -r src/forecasting/requirements.txt -r src/dashboard/requirements.txt
& ./.runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/setup_local_postgres.py
& ./.runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/warehouse.py all
& ./src/dashboard/run_dashboard.ps1
```

Chờ mỗi lệnh thành công trước khi chạy lệnh tiếp theo. Script setup tạo và
khởi động PostgreSQL riêng tại `127.0.0.1:55432`, database `superstore_dw`.
`warehouse.py all` tạo cấu trúc, nạp dữ liệu processed và xuất kết quả đối soát/OLAP.
Các biến kết nối trong terminal phải trỏ đúng kho này; nếu trước đó đã đặt
`SUPERSTORE_DATABASE_URL`, `PGPASSFILE` hoặc `PSQL_PATH` cho kho khác, dùng
một terminal không có các cấu hình đó cho quy trình cục bộ.

Sau lần cài đặt/nạp kho đầu tiên, khởi động lại bằng:

```powershell
& ./src/dashboard/run_dashboard.ps1
```

Script dùng đúng `.runtime/forecast-venv/Scripts/python.exe`, khởi động kho
cục bộ rồi chạy Streamlit. Script không tự tạo venv, cài dependency hoặc nạp
dữ liệu. Mở `http://127.0.0.1:8501`; nhấn Ctrl+C trong terminal để dừng
Streamlit. Thao tác này không tự dừng PostgreSQL.

Nếu PowerShell chặn chạy file `.ps1`, sau khi setup và nạp kho thành công,
có thể chạy trực tiếp lệnh tương đương mà không đổi execution policy:

```powershell
& ./.runtime/forecast-venv/Scripts/python.exe -m streamlit run src/dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

## Dùng PostgreSQL đã có hoặc triển khai Cloud

Với kho đã có và đã nạp dữ liệu, cấu hình `SUPERSTORE_DATABASE_URL` và
`PGPASSFILE` cho kết nối của bạn, sau đó dùng lệnh Streamlit trực tiếp ở trên.
`PSQL_PATH` cần cho các lệnh quản lý/kiểm tra kho bằng `warehouse.py`.
Không dùng launcher cục bộ khi chỉ muốn kết nối kho bên ngoài, vì launcher
luôn gọi script setup PostgreSQL cục bộ.

Đối với cấu hình Streamlit Cloud của dự án, dùng repository
`thydo26072006-lab/Data-Warehouse`, branch **DNNB**, entrypoint
`src/dashboard/app.py`. Chi tiết Secrets nằm trong [hướng dẫn chung](../../docs/BTL_KHODL_HUONG_DAN.md).
Không commit `.runtime/`, tệp pgpass, mật khẩu hoặc API key.

## Kiểm tra

Sau khi kho hoạt động và kết nối đúng, chạy từ gốc repo:

```powershell
& ./.runtime/forecast-venv/Scripts/python.exe -X utf8 src/warehouse/warehouse.py verify
& ./.runtime/forecast-venv/Scripts/python.exe -X utf8 src/dashboard/check_dashboard.py
& ./.runtime/forecast-venv/Scripts/python.exe -X utf8 src/dashboard/test_chatbot_windows.py
```

Bằng chứng đã lưu xem tại [evidence](../../evidence/README.md) và
[kiểm thử cửa sổ chatbot](../../evidence/chatbot-windows/README.md).

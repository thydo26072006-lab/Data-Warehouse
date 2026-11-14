# CO4031 — Kho dữ liệu và Hệ hỗ trợ Quyết định

**Học kỳ 261 · Lớp L02 · Nhóm 5 · Global Superstore**

Nhánh BTL đã đồng bộ bộ tệp theo Mục 5.1 từ `nop-bai/co4031-hk261`. Xem [hướng dẫn chạy trên Windows, Streamlit Cloud và ghi chú phát triển](docs/BTL_KHODL_HUONG_DAN.md).

| Thành phần | Vị trí |
| --- | --- |
| Báo cáo PDF | [KDL_Main.pdf](KDL_Main.pdf) — báo cáo TeXPage hiện có và phụ lục CV04 ở cuối PDF |
| Slide thuyết trình PDF | [Slide_CO4031.pdf](Slide_CO4031.pdf) — 44 slide |
| Mã nguồn SQL, ETL, OLAP, DSS, Streamlit | [src/](src/) |
| Dữ liệu gốc và dữ liệu đã xử lý | [data/](data/) — 51.290 dòng, nguồn [Global Superstore trên Kaggle](https://www.kaggle.com/datasets/fatihilhan/global-superstore-dataset) |
| Kết quả Holt–Winters và 12 truy vấn OLAP | [results/forecasting/](results/forecasting/) và [results/warehouse/olap/](results/warehouse/olap/) |
| Kiểm định và mã tái lập Monte Carlo | [results/monte_carlo/](results/monte_carlo/), [tools/evaluate_monte_carlo.py](tools/evaluate_monte_carlo.py) và [evidence/](evidence/) |

## Chạy hệ thống

Cần Python 3.12, PostgreSQL và tiện ích dòng lệnh `psql`. Sau khi tạo và kích hoạt môi trường Python, cài thư viện từ thư mục gốc:

```bash
python -m pip install -r src/dashboard/requirements.txt -r src/forecasting/requirements.txt
```

1. Tạo một cơ sở dữ liệu PostgreSQL trống. Thiết lập `SUPERSTORE_DATABASE_URL` với chuỗi kết nối tới cơ sở dữ liệu đó. Không commit thông tin kết nối.
2. Chạy các lệnh sau từ gốc repo. Có thể dùng dữ liệu processed và kết quả Holt–Winters đã kèm sẵn nếu dữ liệu kho khớp với bản nộp.

```bash
python src/etl/preprocess.py --check-baseline
python src/warehouse/warehouse.py all
python src/forecasting/forecast.py
python -m streamlit run src/dashboard/app.py
```

## Kiểm tra có thể chạy độc lập

```bash
python -m unittest discover -s src/etl -p test_preprocess.py -v
python -m unittest discover -s src/dashboard -p test_daily_customers.py -v
python tools/evaluate_monte_carlo.py
```

- Bản bàn giao này đã chạy lại 8 kiểm thử ETL, 9 kiểm thử Monte Carlo và tái lập kết quả backtest từ CSV. Không suy rộng thành nghiệm thu PostgreSQL, Streamlit Cloud hoặc Gemini trên môi trường hiện tại.
- Báo cáo gốc chưa biên tập lại toàn bộ LaTeX. Khi nội dung về kiểm định Monte Carlo khác với phụ lục, dùng kết quả CV04 ở cuối PDF và trong `results/monte_carlo/`. WAPE gộp là 32,61% so với 21,53% của đối chứng, với 0/24 tháng thực tế trong dải P10–P90.
- Bằng chứng CV04 giữ nguyên theo manifest. Tài liệu CV04 có chỗ ghi tên log cũ `monte-carlo-tests-final.log`. Tên đúng trong nhánh này là [monte-carlo-tests-cv04.log](evidence/monte-carlo-tests-cv04.log).
- Theo đề bài, nếu nhóm thuyết trình qua video, cần thêm liên kết có quyền xem vào **bìa báo cáo** trước khi nộp LMS. Nhánh này chưa kèm liên kết video vì chưa có URL được xác nhận.

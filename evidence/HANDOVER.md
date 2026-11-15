# Manifest bàn giao nhánh DNNB

[handover-manifest.json](handover-manifest.json) kiểm kê phiên bản bàn giao
sau các lần bổ sung tài liệu và chỉnh PowerPoint. Trường `base_commit` là
commit trước khi thêm bộ manifest này, không phải commit đã chạy toàn bộ test.
Danh sách `files` ghi đường dẫn, số byte và SHA-256 của **toàn bộ tệp được Git
theo dõi**, kể cả hướng dẫn này và script xác minh. Manifest không ghi hash
của chính nó để tránh tham chiếu vòng. Runtime, bí mật, tệp bị ignore và ZIP
nộp LMS không thuộc kiểm kê.

## Kiểm tra tính toàn vẹn

Chạy từ gốc repo có Python 3.12 và Git:

```powershell
python tools/verify_handover_manifest.py
```

Script kiểm tra đủ danh sách tệp được Git theo dõi, số byte và SHA-256 trên
máy. Nếu Git tự đổi LF/CRLF khi clone, hash theo byte có thể khác; để tái lập
nguyên byte, clone với `git -c core.autocrlf=false clone --branch DNNB
--single-branch https://github.com/thydo26072006-lab/Data-Warehouse.git`.
Kết quả PASS xác nhận tính toàn vẹn tệp, không xác nhận một lần kiểm thử mới.

## Phạm vi bằng chứng

| Bằng chứng lịch sử | Phạm vi |
| --- | --- |
| [manifest.json](manifest.json) | Lượt nghiệm thu kho và Dashboard trước khi bổ sung xử lý cửa sổ chatbot |
| [chatbot-windows/manifest.json](chatbot-windows/manifest.json) | 8/8 test cửa sổ chatbot và 21/21 test hồi quy Dashboard sau phần bổ sung |
| [cv04-manifest.json](cv04-manifest.json) | 9/9 test Monte Carlo và kết quả kiểm định CV04 tại thời điểm ghi nhận |

Các manifest trên giữ nguyên byte. `historical_manifest_comparison` trong
manifest bàn giao liệt kê tệp đã thay đổi so với hash lịch sử, không sửa hash
cũ để làm chúng khớp bản mới. `files` là hash bàn giao hiện tại; hash trong
manifest lịch sử tiếp tục mô tả phiên bản kiểm thử tương ứng.

Các kết quả được kế thừa từ log đã có: **21/21 Dashboard, 7/7 tích hợp kho,
8/8 test cửa sổ chatbot**. Việc tạo manifest không chạy lại các bộ test này.
Các lần sửa `tools/evaluate_monte_carlo.py` chỉ bổ sung ghi chú tài liệu;
không suy ra có một lần chạy Monte Carlo mới trên script sau bổ sung.
Môi trường kiểm thử trước đó là Windows, Python 3.12.6, PostgreSQL 17.11.
Neon, Streamlit Cloud và Gemini API thật chưa được nghiệm thu trong bộ này.

Manifest kiểm kê cả PowerPoint mới và PDF slide đang có như hai tệp riêng;
không xác nhận nội dung hai tệp đồng bộ. Mọi lần sửa hoặc thêm tệp sau bản
chốt này cần manifest bàn giao mới để tiếp tục xác minh toàn bộ phiên bản.

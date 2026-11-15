# Kiểm thử phần bổ sung cửa sổ khách hàng

- `test_chatbot_windows-final.log`: 8/8 kiểm thử bổ sung đạt, không cần database.
- `check_dashboard.log`: 21/21 kiểm thử hồi quy Dashboard đạt trên PostgreSQL cục bộ.
- `../../results/dashboard/checks.json`: kết quả có cấu trúc từ lượt Dashboard mới.
- `manifest.json`: môi trường, hash mã nguồn và bằng chứng cho phần bổ sung.

`test_chatbot_windows.log` giữ lại lượt thử ban đầu: 7 đạt, 1 thất bại vì
assertion của test mới thiếu cụm “khách hoạt động” trong chuỗi mong đợi.
Sau khi sửa assertion của test mới cho đúng định dạng phản hồi, chạy lại được
8/8 trong log `-final`. Không thay đổi mã ứng dụng giữa hai lượt này.

Các log/manifest ở thư mục `evidence/` cấp trên vẫn là bằng chứng lịch sử
của phiên bản trước; không bị ghi đè bởi lần kiểm thử này.

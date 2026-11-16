# Bàn giao sau khi cập nhật PDF slide

> **Cập nhật lệnh kiểm tra manifest:** Chạy `python tools/verify_handover_manifest.py`
> để tự chọn manifest bàn giao mới nhất theo `created_at` có múi giờ trong
> `evidence/handover*-manifest.json` (loại `handover_file_inventory`). Script
> in đường dẫn manifest đã chọn. Bản cập nhật hiện tại là
> [handover-default-manifest.json](handover-default-manifest.json).
> Có thể chỉ định tệp bằng `python tools/verify_handover_manifest.py evidence/handover-default-manifest.json`.
> Các lệnh dẫn manifest cũ bên dưới được giữ làm lịch sử; kiểm tra chúng trên
> repo hiện tại có thể báo khác hash hoặc danh sách tệp vì phiên bản đã thay đổi.


Manifest mới nhất cho lần cập nhật PDF slide là
[handover-slides-manifest.json](handover-slides-manifest.json).
Manifest bàn giao trước đó được giữ nguyên làm lịch sử.

Kiểm tra từ thư mục gốc repo:

```powershell
python tools/verify_handover_manifest.py evidence/handover-slides-manifest.json
```

`Slide_CO4031.pdf` được sao nguyên byte từ bản người dùng xuất tại
`MThy_REPO/Data-Warehouse-import-btl-khodl/Slide_CO4031.pdf`.
Đã kiểm tra 44 trang và các chỉnh sửa tham chiếu, cấu hình Monte Carlo,
số trang 39–40. PowerPoint trên nhánh được giữ nguyên.
Đây là cập nhật tài liệu, không chạy lại kiểm thử ứng dụng.

Manifest kiểm kê tất cả tệp Git theo dõi của lần bàn giao này, trừ chính nó;
bao gồm cả manifest trước đó. Hash theo byte, không chuẩn hóa LF/CRLF.
Các manifest kiểm thử lịch sử vẫn mô tả các phiên bản tại thời điểm chạy.
